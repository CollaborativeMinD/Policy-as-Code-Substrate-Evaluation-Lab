"""Generate an independent v2.0.0 reference answer in the extracted archive."""
import json
from Resources import catalog, compose, evaluate, example


def baseline_answers():
    cases = [(p["id"].replace(".", "-").replace("_", "-"), {"substrate": p["id"]}, 0) for p in catalog()]
    ground = "ugv.clearpath_jackal.v3"
    pi = "controller.raspberry_pi5_8gb.v1"
    cases.extend([
        ("jackal-pi-traction", {"substrate": ground, "compute": pi,
         "wounds": [{"id":"traction_loss", "severity":0.5}]}, 2),
        ("panda-source", {"substrate":"robotic.franka_panda.v4","source_ref":"fixture:bench-torque-envelope",
         "source_payload":{"joint_dynamics":{"torque_limits":[8,8,8,8,2,2,2]}}}, 0),
        ("pi-loop-budget", {"substrate":pi, "overrides":{"loop_budget_s":0.1}}, 0),
        ("pi-thermal", {"substrate":pi, "wounds":[{"id":"thermal_rise", "severity":1.0}]}, 0),
        ("jackal-no-traction", {"substrate":ground, "wounds":[{"id":"traction_loss", "severity":1.0}]}, 0),
    ])
    results = {}
    for name, arguments, time_s in cases:
        config = compose(**arguments)
        observations = example(config)
        if name == "pi-loop-budget":
            observations["loop_time_s"] = 0.2
        results[name] = [config.to_dict(), evaluate(config, observations, time_s=time_s)]
    return results


if __name__ == "__main__":
    print(json.dumps(baseline_answers(), allow_nan=False))
