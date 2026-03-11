import sys
import os
import runpy

project_root = r'E:\Sharing bike\FleetPy-main\FleetPy-main'
sys.path.insert(0, project_root)

# Set the working directory to the project root to ensure relative paths work
os.chdir(project_root)

# Now, run the study module
# The -m argument expects a module name (e.g., studies.bike_rebalancing_study.01_run_study)
# runpy.run_module can execute a module like python -m does
module_name = 'studies.bike_rebalancing_study.01_run_study'

print(f"Attempting to run module: {module_name} from project root: {project_root}")

try:
    runpy.run_module(module_name, run_name="__main__", alter_sys=True)
except Exception as e:
    print(f"Error running module {module_name}: {e}")
    import traceback
    traceback.print_exc()
