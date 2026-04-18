#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from smart_ac_core import SmartACModel


def print_front_window(
    cfg,
    outdoor_temps: list[float],
    pid,
    mpc,
    front_step: int,
) -> None:
    start = max(0, front_step - 6)
    end = min(cfg.steps, front_step + 10)

    print("\nCold-front window")
    print("step  hour  out[C]  pid[C]  pid[%]  mpc[C]  mpc[%]  residual[C]  bias[C]")
    for step in range(start, end):
        print(
            f"{step:>4}  {step * cfg.dt_hours:>4.1f}  {outdoor_temps[step]:>6.1f}  "
            f"{pid.actual_temps[step]:>6.2f}  {pid.controls[step] * 100:>6.0f}  "
            f"{mpc.actual_temps[step]:>6.2f}  {mpc.controls[step] * 100:>6.0f}  "
            f"{mpc.residuals[step + 1]:>11.2f}  {mpc.bias_corrections[step + 1]:>7.2f}"
        )


def write_csv_report(
    output_path: Path,
    cfg,
    outdoor_temps: list[float],
    pid,
    mpc,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "step",
                "hour",
                "outdoor_temp_c",
                "pid_room_temp_c",
                "pid_power_pct",
                "mpc_actual_room_temp_c",
                "mpc_measured_room_temp_c",
                "mpc_power_pct",
                "mpc_residual_c",
                "mpc_bias_correction_c",
                "mpc_solve_time_ms",
            ]
        )
        for step in range(cfg.steps):
            writer.writerow(
                [
                    step,
                    round(step * cfg.dt_hours, 3),
                    round(outdoor_temps[step], 3),
                    round(pid.actual_temps[step], 3),
                    round(pid.controls[step] * 100.0, 1),
                    round(mpc.actual_temps[step], 3),
                    round(mpc.measured_temps[step], 3),
                    round(mpc.controls[step] * 100.0, 1),
                    round(mpc.residuals[step + 1], 3),
                    round(mpc.bias_corrections[step + 1], 3),
                    round(mpc.solve_times_ms[step], 3),
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple CLI for the Smart-AC MPC example")
    parser.add_argument(
        "--csv",
        default="artifacts/smart_ac_cli.csv",
        help="Optional CSV output path",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip writing the CSV report",
    )
    args = parser.parse_args()

    model = SmartACModel()
    cfg = model.scenario
    outdoor_temps = model.outdoor_profile()
    noise = model.sensor_noise()
    pid = model.run_pid(outdoor_temps, noise)
    mpc = model.run_mpc(outdoor_temps, noise)
    front_step = cfg.cold_front_start_step
    pid_max_temp = max(pid.actual_temps)
    mpc_max_temp = max(mpc.actual_temps)
    pid_temp_swing = pid_max_temp - pid.min_temp
    mpc_temp_swing = mpc_max_temp - mpc.min_temp
    pid_overshoot = max(0.0, pid_max_temp - cfg.comfort_high)
    mpc_overshoot = max(0.0, mpc_max_temp - cfg.comfort_high)

    print("Smart-AC CLI")
    print("============")
    print(f"Time step              : {cfg.dt_hours * 60:.0f} min")
    print(f"Prediction horizon     : {cfg.mpc_horizon_steps} steps ({cfg.mpc_horizon_steps * cfg.dt_hours:.1f} h)")
    print(f"Cold front starts      : step {front_step} ({front_step * cfg.dt_hours:.2f} h)")
    print(f"Cold front minimum     : {cfg.cold_front_min_temp:.1f} C")
    print(f"Comfort band (CV)      : {cfg.comfort_low:.1f} C to {cfg.comfort_high:.1f} C")
    print(f"Manipulated variable   : HVAC power u[k] in 0% to 100%")
    print(f"Disturbance forecast   : outdoor temperature Tout[k]")
    print(f"PID baseline           : Kp={cfg.pid_kp:.2f}, Ki={cfg.pid_ki:.2f}, Kd={cfg.pid_kd:.2f}")
    print()
    print(
        f"PID controller         : min {pid.min_temp:.2f} C, "
        f"energy {pid.energy_kwh:.2f} kWh, violations {pid.comfort_violations}"
    )
    print(
        f"Forecast-aware MPC     : min {mpc.min_temp:.2f} C, "
        f"energy {mpc.energy_kwh:.2f} kWh, violations {mpc.comfort_violations}"
    )
    print(f"Temperature swing      : MPC {mpc_temp_swing:.2f} C / PID {pid_temp_swing:.2f} C")
    print(f"Peak overshoot         : MPC {mpc_overshoot:.2f} C / PID {pid_overshoot:.2f} C")
    print(
        f"MPC solve time         : avg {sum(mpc.solve_times_ms) / len(mpc.solve_times_ms):.2f} ms, "
        f"max {max(mpc.solve_times_ms):.2f} ms, total {sum(mpc.solve_times_ms):.2f} ms"
    )
    print(model.simulate()["narrative"]["summary"])

    print("\nTerminology map")
    print("CV : room temperature x[k]")
    print("MV : HVAC command u[k]")
    print("Measured value y[k] : noisy room temperature sensor")
    print("Prediction error : y[k] - predicted_next[k]")
    print("Bias correction z[k] : offset added to the controller model")
    print("Receding horizon : plan many steps ahead, apply only the first move")

    print_front_window(cfg, outdoor_temps, pid, mpc, front_step)

    if not args.no_csv:
        output_path = Path(args.csv)
        write_csv_report(output_path, cfg, outdoor_temps, pid, mpc)
        print(f"\nCSV output: {output_path}")


if __name__ == "__main__":
    main()
