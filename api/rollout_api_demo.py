import requests
import time
import json

API_SERVER_URL = "http://localhost:5000/api"

def create_env():
    print("\nAttempting to create environment...")
    try:
        response = requests.post(f"{API_SERVER_URL}/env/create")
        response.raise_for_status() # Raise an exception for bad status codes
        result = response.json()
        print(f"Create Env Response: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error creating environment: {e}")
        return None

def step_env(trajectory_id: str, command: str):
    print(f"\nAttempting to step with command '{command}' for trajectory {trajectory_id}...")
    payload = {
        "trajectory_id": trajectory_id,
        "command": command
    }
    try:
        response = requests.post(f"{API_SERVER_URL}/env/step", json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"Step Env Response: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error stepping environment: {e}")
        return None

def save_env(trajectory_id: str):
    print(f"\nAttempting to save environment for trajectory {trajectory_id}...")
    payload = {"trajectory_id": trajectory_id}
    try:
        response = requests.post(f"{API_SERVER_URL}/env/save", json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"Save Env Response: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error saving environment: {e}")
        return None

def calculate_reward(trajectory_id: str, reward_type: str, actions: list, observations: list, success_flag: bool):
    print(f"\nAttempting to calculate reward for trajectory {trajectory_id}...")
    # Construct trajectory_data similar to what RewardWorker expects
    # This might need adjustment based on actual RewardWorker implementation details
    trajectory_data = {
        "actions": actions,
        "states": observations, # Assuming observations can stand in for states for demo
        "success": success_flag
        # Add other fields like 'goal' if your reward functions need them
    }
    payload = {
        "trajectory_id": trajectory_id,
        "reward_type": reward_type,
        "trajectory_data": trajectory_data
    }
    try:
        response = requests.post(f"{API_SERVER_URL}/reward/calculate", json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"Calculate Reward Response: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error calculating reward: {e}")
        return None

def remove_env(trajectory_id: str):
    print(f"\nAttempting to remove environment for trajectory {trajectory_id}...")
    payload = {"trajectory_id": trajectory_id}
    try:
        response = requests.post(f"{API_SERVER_URL}/env/remove", json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"Remove Env Response: {result}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error removing environment: {e}")
        return None

def run_rollout_demo():
    print("===== Starting API Rollout Demo for Android Environment =====")

    trajectory_id = None
    collected_actions = []
    collected_observations = []

    try:
        # 1. Create environment
        creation_response = create_env()
        if not creation_response or not creation_response.get('success'):
            print("Failed to create environment. Exiting demo.")
            return
        
        trajectory_id = creation_response.get('trajectory_id')
        if not trajectory_id:
            print("No trajectory_id received. Exiting demo.")
            return
        
        print(f"Environment created with trajectory_id: {trajectory_id}")

        # 2. Perform some steps
        commands_to_run = [
            'text "Hello Android from API demo"',
            'key home',
            'screenshot' # To get some observation data
        ]

        for cmd in commands_to_run:
            time.sleep(1) # Small delay between commands
            step_response = step_env(trajectory_id, cmd)
            if step_response and step_response.get('success'):
                collected_actions.append(cmd)
                collected_observations.append(step_response.get('observation', {}))
            else:
                print(f"Failed to execute command: {cmd}. Continuing...")
        
        # 3. Save environment
        save_response = save_env(trajectory_id)
        if not save_response or not save_response.get('success'):
            print("Failed to save environment.")
            # Continue to reward and removal anyway for demo purposes

        # 4. Calculate reward
        # For demo, let's assume the task was a "success" if all commands were attempted.
        # More sophisticated success criteria would be needed in a real scenario.
        rollout_success = len(collected_actions) == len(commands_to_run)
        
        reward_response = calculate_reward(
            trajectory_id,
            reward_type="rule_based", # Assuming a 'rule_based' type exists in RewardWorker
            actions=collected_actions,
            observations=collected_observations,
            success_flag=rollout_success
        )
        if reward_response and reward_response.get('success'):
            print(f"Reward calculated: {reward_response.get('reward')}")
        else:
            print("Failed to calculate reward or reward calculation reported failure.")

    except Exception as e:
        print(f"An unexpected error occurred during the rollout demo: {e}")
    finally:
        # 5. Remove environment (ensure this happens even if errors occur)
        if trajectory_id:
            time.sleep(1)
            remove_env(trajectory_id)
        
        print("\n===== API Rollout Demo Finished =====")

if __name__ == "__main__":
    # Before running, ensure your API server is up:
    # python main.py --mode api --host 0.0.0.0 --port 5000
    # (or however you start it with Android env and RewardWorker registered)
    run_rollout_demo() 