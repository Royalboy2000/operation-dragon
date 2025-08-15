import threading
import uuid
import logging

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()

    def start_task(self, name, target, args=()):
        """Starts a new background task and returns its ID."""
        task_id = str(uuid.uuid4())[:8]
        stop_event = threading.Event()

        # Pass the stop_event as the first argument to the target function
        thread_args = (stop_event,) + args
        thread = threading.Thread(target=target, args=thread_args)
        thread.daemon = True

        with self.lock:
            self.tasks[task_id] = {
                "name": name,
                "thread": thread,
                "stop_event": stop_event
            }

        thread.start()
        logger.info(f"Started task '{name}' with ID: {task_id}")
        return task_id

    def stop_task(self, task_id):
        """Stops a running task."""
        with self.lock:
            task = self.tasks.get(task_id)
            if task and task["thread"].is_alive():
                task["stop_event"].set()
                logger.info(f"Stop signal sent to task {task_id} ({task['name']}).")
                # The thread will stop on its own. We can remove it from the list.
                # A more robust system might wait for the thread to join.
                del self.tasks[task_id]
                return True
            elif task: # Thread is no longer alive
                del self.tasks[task_id]
        return False

    def list_tasks(self):
        """Returns a dictionary of active tasks and their names."""
        with self.lock:
            # Prune dead threads before returning the list
            dead_tasks = [task_id for task_id, task in self.tasks.items() if not task["thread"].is_alive()]
            for task_id in dead_tasks:
                del self.tasks[task_id]

            return {task_id: task["name"] for task_id, task in self.tasks.items()}

# Global instance of the task manager
task_manager = TaskManager()
