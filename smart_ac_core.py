from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Scenario:
    dt_hours: float = 10.0 / 60.0
    steps: int = 72
    initial_room_temp: float = 23.1
    comfort_low: float = 22.0
    comfort_high: float = 24.0
    min_safe_temp: float = 18.0
    max_power_kw: float = 3.2
    model_leak_rate: float = 0.012
    model_heater_gain: float = 0.72
    plant_leak_rate: float = 0.0135
    plant_heater_gain: float = 0.67
    mpc_horizon_steps: int = 18
    temp_grid_min: float = 18.0
    temp_grid_max: float = 27.0
    temp_grid_step: float = 0.25
    control_levels: tuple[float, ...] = tuple(level / 10.0 for level in range(11))
    bias_alpha: float = 0.45
    sensor_noise_sigma: float = 0.35
    seed: int = 7
    cold_front_start_step: int = 21
    pid_target_temp: float = 23.0
    pid_kp: float = 0.42
    pid_ki: float = 0.10
    pid_kd: float = 0.30


@dataclass
class ControllerRun:
    label: str
    actual_temps: list[float]
    measured_temps: list[float]
    controls: list[float]
    energy_kwh: float
    min_temp: float
    comfort_violations: int


@dataclass
class MPCTrace:
    actual_temps: list[float]
    measured_temps: list[float]
    controls: list[float]
    predicted_next_temps: list[float]
    residuals: list[float]
    bias_corrections: list[float]
    solve_times_ms: list[float]
    plan_controls: list[list[float]]
    plan_temps: list[list[float]]
    energy_kwh: float
    min_temp: float
    comfort_violations: int


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _build_outdoor_profile(cfg: Scenario) -> list[float]:
    front_hour = cfg.cold_front_start_step * cfg.dt_hours
    anchors = [
        (front_hour - 3.5, 14.0),
        (front_hour - 2.5, 13.5),
        (front_hour - 1.5, 12.0),
        (front_hour - 0.5, 8.0),
        (front_hour + 0.0, 2.0),
        (front_hour + 0.5, -4.0),
        (front_hour + 1.5, -6.0),
        (front_hour + 2.5, -2.0),
        (front_hour + 3.5, 2.0),
        (front_hour + 4.5, 6.0),
        (front_hour + 6.5, 9.0),
        (front_hour + 8.5, 11.0),
    ]
    profile: list[float] = []
    for step in range(cfg.steps + 1):
        hour = step * cfg.dt_hours
        for left, right in zip(anchors, anchors[1:]):
            if left[0] <= hour <= right[0]:
                ratio = (hour - left[0]) / (right[0] - left[0])
                profile.append(left[1] + ratio * (right[1] - left[1]))
                break
        else:
            profile.append(anchors[-1][1])
    return profile


def _build_sensor_noise(cfg: Scenario) -> list[float]:
    rng = random.Random(cfg.seed)
    return [rng.gauss(0.0, cfg.sensor_noise_sigma) for _ in range(cfg.steps + 1)]


def _plant_dynamics(room_temp: float, outdoor_temp: float, power: float, step: int, cfg: Scenario) -> float:
    leak_rate = cfg.plant_leak_rate
    heater_gain = cfg.plant_heater_gain
    extra_disturbance = 0.0
    if step >= cfg.cold_front_start_step:
        leak_rate += 0.0035
    if cfg.cold_front_start_step <= step <= cfg.cold_front_start_step + 2:
        extra_disturbance -= 0.28
    if cfg.cold_front_start_step + 9 <= step <= cfg.cold_front_start_step + 15:
        heater_gain -= 0.03
    return room_temp + leak_rate * (outdoor_temp - room_temp) + heater_gain * power + extra_disturbance


def _controller_dynamics(room_temp: float, outdoor_temp: float, power: float, bias: float, cfg: Scenario) -> float:
    return room_temp + cfg.model_leak_rate * (outdoor_temp - room_temp) + cfg.model_heater_gain * power + bias


def _pid_controller(
    measured_temp: float,
    integral_error: float,
    previous_error: float,
    cfg: Scenario,
) -> tuple[float, float, float]:
    error = cfg.pid_target_temp - measured_temp
    derivative = error - previous_error
    candidate_integral = clamp(integral_error + error, -15.0, 15.0)
    control = cfg.pid_kp * error + cfg.pid_ki * candidate_integral + cfg.pid_kd * derivative
    saturated = clamp(control, 0.0, 1.0)
    if (control > 1.0 and error > 0.0) or (control < 0.0 and error < 0.0):
        candidate_integral = integral_error
    return saturated, candidate_integral, error


def _comfort_penalty(temp: float, cfg: Scenario) -> float:
    center_penalty = 0.8 * (temp - 23.0) ** 2
    band_distance = 0.0
    if temp < cfg.comfort_low:
        band_distance = cfg.comfort_low - temp
    elif temp > cfg.comfort_high:
        band_distance = temp - cfg.comfort_high
    return center_penalty + 60.0 * band_distance**2


def _build_temperature_grid(cfg: Scenario) -> list[float]:
    count = int(round((cfg.temp_grid_max - cfg.temp_grid_min) / cfg.temp_grid_step)) + 1
    return [cfg.temp_grid_min + index * cfg.temp_grid_step for index in range(count)]


def _interpolate_cost(temp: float, grid: list[float], costs: list[float]) -> float:
    if temp <= grid[0]:
        return costs[0] + 500.0 * (grid[0] - temp)
    if temp >= grid[-1]:
        return costs[-1] + 50.0 * (temp - grid[-1])
    raw_index = (temp - grid[0]) / (grid[1] - grid[0])
    lower_index = int(math.floor(raw_index))
    upper_index = lower_index + 1
    ratio = raw_index - lower_index
    return costs[lower_index] * (1.0 - ratio) + costs[upper_index] * ratio


def _compute_cost_to_go(
    forecast: list[float],
    bias: float,
    cfg: Scenario,
    temp_grid: list[float],
) -> list[list[float]]:
    horizon = len(forecast)
    tables: list[list[float]] = [[] for _ in range(horizon + 1)]
    tables[horizon] = [_comfort_penalty(temp, cfg) for temp in temp_grid]
    for offset in range(horizon - 1, -1, -1):
        next_costs = tables[offset + 1]
        costs_at_step: list[float] = []
        for temp in temp_grid:
            best_cost = math.inf
            for power in cfg.control_levels:
                next_temp = _controller_dynamics(temp, forecast[offset], power, bias, cfg)
                if next_temp < cfg.min_safe_temp:
                    continue
                stage_cost = _comfort_penalty(next_temp, cfg) + 1.8 * power**2
                candidate = stage_cost + _interpolate_cost(next_temp, temp_grid, next_costs)
                if candidate < best_cost:
                    best_cost = candidate
            costs_at_step.append(best_cost)
        tables[offset] = costs_at_step
    return tables


def _choose_best_action(
    room_temp: float,
    outdoor_temp: float,
    next_costs: list[float],
    bias: float,
    cfg: Scenario,
    temp_grid: list[float],
) -> tuple[float, float]:
    best_power = 0.0
    best_temp = room_temp
    best_cost = math.inf
    for power in cfg.control_levels:
        next_temp = _controller_dynamics(room_temp, outdoor_temp, power, bias, cfg)
        if next_temp < cfg.min_safe_temp:
            continue
        stage_cost = _comfort_penalty(next_temp, cfg) + 1.8 * power**2
        candidate = stage_cost + _interpolate_cost(next_temp, temp_grid, next_costs)
        if candidate < best_cost:
            best_cost = candidate
            best_power = power
            best_temp = next_temp
    return best_power, best_temp


def _choose_mpc_plan(
    room_temp: float,
    forecast: list[float],
    bias: float,
    cfg: Scenario,
    temp_grid: list[float],
) -> tuple[float, float, list[float], list[float]]:
    if not forecast:
        return 0.0, room_temp, [], [room_temp]
    horizon_forecast = forecast[: cfg.mpc_horizon_steps]
    tables = _compute_cost_to_go(horizon_forecast, bias, cfg, temp_grid)
    planned_controls: list[float] = []
    planned_temps = [room_temp]
    plan_temp = room_temp
    first_power = 0.0
    first_prediction = room_temp
    for offset, outdoor_temp in enumerate(horizon_forecast):
        next_costs = tables[offset + 1]
        best_power, next_temp = _choose_best_action(plan_temp, outdoor_temp, next_costs, bias, cfg, temp_grid)
        planned_controls.append(best_power)
        planned_temps.append(next_temp)
        if offset == 0:
            first_power = best_power
            first_prediction = next_temp
        plan_temp = next_temp
    return first_power, first_prediction, planned_controls, planned_temps


def _summarize_preheating(mpc: MPCTrace, pid: ControllerRun, front_step: int, cfg: Scenario) -> str:
    mpc_start = next((step for step, power in enumerate(mpc.controls[:front_step]) if power > 0.05), None)
    pid_start = next((step for step, power in enumerate(pid.controls[:front_step]) if power > 0.05), None)
    if mpc_start is None:
        return "今回の設定では、MPC は寒波前に先回り加熱しませんでした。"
    if pid_start is None:
        lead = int(round((front_step - mpc_start) * cfg.dt_hours * 60.0))
        return f"MPC は寒波の {lead} 分前から先回り加熱を始め、PID 制御はそれまで待っていました。"
    lead = int(round((pid_start - mpc_start) * cfg.dt_hours * 60.0))
    if lead > 0:
        return f"MPC は PID 制御より {lead} 分早く暖房を開始しました。"
    return "今回の設定では、MPC と PID 制御はほぼ同じタイミングで暖房を始めました。"


class SmartACModel:
    def __init__(self, scenario: Scenario | None = None):
        self.scenario = self._normalize_scenario(scenario or Scenario())

    @staticmethod
    def _normalize_scenario(cfg: Scenario) -> Scenario:
        steps = max(24, int(round(cfg.steps)))
        comfort_low = float(cfg.comfort_low)
        comfort_high = max(float(cfg.comfort_high), comfort_low + 0.5)
        min_safe_temp = min(float(cfg.min_safe_temp), comfort_low)
        horizon = min(max(3, int(round(cfg.mpc_horizon_steps))), steps)
        control_levels = tuple(float(value) for value in cfg.control_levels)
        if not control_levels:
            control_levels = tuple(level / 10.0 for level in range(11))
        cold_front_start_step = min(max(0, int(round(cfg.cold_front_start_step))), steps - 1)
        return Scenario(
            dt_hours=float(cfg.dt_hours),
            steps=steps,
            initial_room_temp=float(cfg.initial_room_temp),
            comfort_low=comfort_low,
            comfort_high=comfort_high,
            min_safe_temp=min_safe_temp,
            max_power_kw=float(cfg.max_power_kw),
            model_leak_rate=float(cfg.model_leak_rate),
            model_heater_gain=float(cfg.model_heater_gain),
            plant_leak_rate=float(cfg.plant_leak_rate),
            plant_heater_gain=float(cfg.plant_heater_gain),
            mpc_horizon_steps=horizon,
            temp_grid_min=float(cfg.temp_grid_min),
            temp_grid_max=float(cfg.temp_grid_max),
            temp_grid_step=float(cfg.temp_grid_step),
            control_levels=control_levels,
            bias_alpha=clamp(float(cfg.bias_alpha), 0.0, 1.0),
            sensor_noise_sigma=max(0.0, float(cfg.sensor_noise_sigma)),
            seed=max(1, int(round(cfg.seed))),
            cold_front_start_step=cold_front_start_step,
            pid_target_temp=float(cfg.pid_target_temp),
            pid_kp=max(0.0, float(cfg.pid_kp)),
            pid_ki=max(0.0, float(cfg.pid_ki)),
            pid_kd=max(0.0, float(cfg.pid_kd)),
        )

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "SmartACModel":
        base = Scenario()
        payload = dict(values)
        if "control_levels" in payload and isinstance(payload["control_levels"], list):
            payload["control_levels"] = tuple(float(value) for value in payload["control_levels"])
        return cls(Scenario(**{**asdict(base), **payload}))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.scenario)

    def outdoor_profile(self) -> list[float]:
        return _build_outdoor_profile(self.scenario)

    def sensor_noise(self) -> list[float]:
        return _build_sensor_noise(self.scenario)

    def run_pid(self, outdoor_temps: list[float], noise: list[float]) -> ControllerRun:
        cfg = self.scenario
        actual_temps = [cfg.initial_room_temp]
        measured_temps = [cfg.initial_room_temp + noise[0]]
        controls: list[float] = []
        integral_error = 0.0
        previous_error = cfg.pid_target_temp - measured_temps[0]
        for step in range(cfg.steps):
            measured_temp = measured_temps[-1]
            power, integral_error, previous_error = _pid_controller(
                measured_temp,
                integral_error,
                previous_error,
                cfg,
            )
            next_actual = _plant_dynamics(actual_temps[-1], outdoor_temps[step], power, step, cfg)
            next_measured = next_actual + noise[step + 1]
            controls.append(power)
            actual_temps.append(next_actual)
            measured_temps.append(next_measured)
        energy = sum(controls) * cfg.dt_hours * cfg.max_power_kw
        violations = sum(temp < cfg.comfort_low or temp > cfg.comfort_high for temp in actual_temps[:-1])
        return ControllerRun(
            label="PID controller",
            actual_temps=actual_temps,
            measured_temps=measured_temps,
            controls=controls,
            energy_kwh=energy,
            min_temp=min(actual_temps),
            comfort_violations=violations,
        )

    def run_mpc(self, outdoor_temps: list[float], noise: list[float]) -> MPCTrace:
        cfg = self.scenario
        temp_grid = _build_temperature_grid(cfg)
        actual_temps = [cfg.initial_room_temp]
        measured_temps = [cfg.initial_room_temp + noise[0]]
        controls: list[float] = []
        predicted_next_temps = [cfg.initial_room_temp]
        residuals = [0.0]
        bias_corrections = [0.0]
        solve_times_ms: list[float] = []
        plan_controls: list[list[float]] = []
        plan_temps: list[list[float]] = []
        current_bias = 0.0
        for step in range(cfg.steps):
            measured_temp = measured_temps[-1]
            if step > 0:
                residual = measured_temp - predicted_next_temps[-1]
                current_bias = (1.0 - cfg.bias_alpha) * current_bias + cfg.bias_alpha * residual
            residuals.append(measured_temp - predicted_next_temps[-1] if step > 0 else 0.0)
            bias_corrections.append(current_bias)
            solve_started = time.perf_counter()
            power, predicted_next, planned_u, planned_x = _choose_mpc_plan(
                measured_temp,
                outdoor_temps[step:],
                current_bias,
                cfg,
                temp_grid,
            )
            solve_times_ms.append((time.perf_counter() - solve_started) * 1000.0)
            next_actual = _plant_dynamics(actual_temps[-1], outdoor_temps[step], power, step, cfg)
            next_measured = next_actual + noise[step + 1]
            controls.append(power)
            plan_controls.append(planned_u)
            plan_temps.append(planned_x)
            predicted_next_temps.append(predicted_next)
            actual_temps.append(next_actual)
            measured_temps.append(next_measured)
        energy = sum(controls) * cfg.dt_hours * cfg.max_power_kw
        violations = sum(temp < cfg.comfort_low or temp > cfg.comfort_high for temp in actual_temps[:-1])
        return MPCTrace(
            actual_temps=actual_temps,
            measured_temps=measured_temps,
            controls=controls,
            predicted_next_temps=predicted_next_temps,
            residuals=residuals,
            bias_corrections=bias_corrections,
            solve_times_ms=solve_times_ms,
            plan_controls=plan_controls,
            plan_temps=plan_temps,
            energy_kwh=energy,
            min_temp=min(actual_temps),
            comfort_violations=violations,
        )

    def simulate(self) -> dict[str, Any]:
        cfg = self.scenario
        outdoor_temps = self.outdoor_profile()
        noise = self.sensor_noise()
        pid = self.run_pid(outdoor_temps, noise)
        mpc = self.run_mpc(outdoor_temps, noise)
        front_step = min(cfg.cold_front_start_step, cfg.steps - 1)
        pid_max_temp = max(pid.actual_temps)
        mpc_max_temp = max(mpc.actual_temps)
        pid_temp_swing = pid_max_temp - pid.min_temp
        mpc_temp_swing = mpc_max_temp - mpc.min_temp
        pid_overshoot = max(0.0, pid_max_temp - cfg.comfort_high)
        mpc_overshoot = max(0.0, mpc_max_temp - cfg.comfort_high)

        plans = []
        for step, planned_temps in enumerate(mpc.plan_temps):
            realized = mpc.actual_temps[step : min(len(mpc.actual_temps), step + len(planned_temps))]
            plans.append(
                {
                    "step": step,
                    "hours": [round((step + idx) * cfg.dt_hours, 3) for idx, _ in enumerate(planned_temps)],
                    "planned_temps": [round(value, 3) for value in planned_temps],
                    "planned_controls": [round(value * 100.0, 1) for value in mpc.plan_controls[step]],
                    "realized_temps": [round(value, 3) for value in realized],
                }
            )

        timeline = []
        for step in range(cfg.steps):
            timeline.append(
                {
                    "step": step,
                    "hour": round(step * cfg.dt_hours, 3),
                    "outdoor_temp_c": round(outdoor_temps[step], 3),
                    "mpc_actual_room_temp_c": round(mpc.actual_temps[step], 3),
                    "mpc_measured_room_temp_c": round(mpc.measured_temps[step], 3),
                    "mpc_power_pct": round(mpc.controls[step] * 100.0, 1),
                    "mpc_predicted_next_c": round(mpc.predicted_next_temps[step + 1], 3),
                    "mpc_residual_c": round(mpc.residuals[step + 1], 3),
                    "mpc_bias_correction_c": round(mpc.bias_corrections[step + 1], 3),
                    "mpc_solve_time_ms": round(mpc.solve_times_ms[step], 3),
                    "pid_room_temp_c": round(pid.actual_temps[step], 3),
                    "pid_power_pct": round(pid.controls[step] * 100.0, 1),
                }
            )

        return {
            "config": self.to_dict(),
            "timeline": timeline,
            "plans": plans,
            "terms": [
                ["CV / 制御変数", "制御したい量", "室温", "mpc_actual_room_temp_c"],
                ["MV / 操作変数", "コントローラが決める入力", "エアコン出力", "mpc_power_pct"],
                ["外乱", "勝手に系を動かす外部要因", "外気温予報", "outdoor_temp_c"],
                ["予測ホライズン", "何ステップ先まで最適化するか", f"{cfg.mpc_horizon_steps} ステップ", "config.mpc_horizon_steps"],
                ["Receding Horizon", "最初の1手だけ実行して毎回解き直すこと", "planned_controls[0] だけ適用", "plans[step].planned_controls"],
                ["制約", "守るべきハード制限", f"室温 >= {cfg.min_safe_temp:.1f} C、出力 0-100%", "min_safe_temp / control_levels"],
                ["1ステップ予測誤差", "予測値と次の実測値の差", "y[k] - predicted_next", "mpc_residual_c"],
                ["オフセット補正 z[k]", "モデルの癖を打ち消す補正量", "モデルに足す温度補正", "mpc_bias_correction_c"],
                ["計算時間", "各 step で最適化にかかった時間", "MPC の解き直し負荷", "mpc_solve_time_ms"],
            ],
            "narrative": {
                "summary": _summarize_preheating(mpc, pid, front_step, cfg),
                "equations": [
                    {
                        "title": "実プラント",
                        "html": "x<sub>k+1</sub> = x<sub>k</sub> + a<sub>real</sub>(T<sub>out,k</sub> - x<sub>k</sub>) + b<sub>real</sub>u<sub>k</sub> + d<sub>k</sub>",
                        "note": "本当の部屋の温度変化。外気温差、暖房出力、追加外乱で次の室温が決まります。",
                        "variables": [
                            ["x_k", "現在の室温"],
                            ["x_{k+1}", "次のステップの室温"],
                            ["T_out,k", "外気温"],
                            ["a_real", "実プラントの漏れ係数"],
                            ["b_real", "実プラントの暖房ゲイン"],
                            ["u_k", "暖房出力"],
                            ["d_k", "追加外乱"],
                        ],
                    },
                    {
                        "title": "センサー",
                        "html": "y<sub>k</sub> = x<sub>k</sub> + noise<sub>k</sub>",
                        "note": "コントローラが見ている観測値です。真の室温にノイズが乗ります。",
                        "variables": [
                            ["y_k", "センサーが観測した温度"],
                            ["x_k", "真の室温"],
                            ["noise_k", "観測ノイズ"],
                        ],
                    },
                    {
                        "title": "制御モデル",
                        "html": "x<sub>model,k+1</sub> = x<sub>k</sub> + a(T<sub>out,k</sub> - x<sub>k</sub>) + bu<sub>k</sub> + z<sub>k</sub>",
                        "note": "MPC が頭の中で使う予測モデルです。実プラントとはわざと少しずらしています。",
                        "variables": [
                            ["x_model,k+1", "MPC が予測する次の室温"],
                            ["x_k", "現在の室温"],
                            ["T_out,k", "外気温予報"],
                            ["a", "モデル漏れ係数"],
                            ["b", "モデル暖房ゲイン"],
                            ["u_k", "暖房出力"],
                            ["z_k", "モデル誤差を打ち消す補正量"],
                        ],
                    },
                    {
                        "title": "補正更新",
                        "html": "z<sub>k</sub> = (1-α)z<sub>k-1</sub> + α(y<sub>k</sub> - x<sub>model,k|k-1</sub>)",
                        "note": "前回予測と実測のずれを使って、モデルの癖を少しずつ補正します。",
                        "variables": [
                            ["z_k", "今回の補正量"],
                            ["z_{k-1}", "前回の補正量"],
                            ["α", "補正ゲイン"],
                            ["y_k", "今回の実測温度"],
                            ["x_model,k|k-1", "前回時点で予測した今回温度"],
                        ],
                    },
                ],
                "front_step": front_step,
                "front_hour": round(front_step * cfg.dt_hours, 3),
            },
            "metrics": {
                "pid_min_temp_c": round(pid.min_temp, 3),
                "pid_max_temp_c": round(pid_max_temp, 3),
                "pid_temp_swing_c": round(pid_temp_swing, 3),
                "pid_overshoot_c": round(pid_overshoot, 3),
                "pid_energy_kwh": round(pid.energy_kwh, 3),
                "pid_violations": pid.comfort_violations,
                "mpc_min_temp_c": round(mpc.min_temp, 3),
                "mpc_max_temp_c": round(mpc_max_temp, 3),
                "mpc_temp_swing_c": round(mpc_temp_swing, 3),
                "mpc_overshoot_c": round(mpc_overshoot, 3),
                "mpc_energy_kwh": round(mpc.energy_kwh, 3),
                "mpc_violations": mpc.comfort_violations,
                "mpc_avg_solve_time_ms": round(sum(mpc.solve_times_ms) / len(mpc.solve_times_ms), 3),
                "mpc_max_solve_time_ms": round(max(mpc.solve_times_ms), 3),
                "mpc_total_solve_time_ms": round(sum(mpc.solve_times_ms), 3),
            },
        }
