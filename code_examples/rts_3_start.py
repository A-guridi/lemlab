import lemlab


if __name__ == "__main__":
    sim_name = "test_rts"

    simulation = lemlab.ScenarioExecutor(path_scenario=f"../scenarios/{sim_name}",
                                         path_results=f"../simulation_results/{sim_name}")
    simulation.run()
