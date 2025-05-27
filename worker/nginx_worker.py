import subprocess
import os
import signal
import time
import shutil
from typing import Dict, Any, Optional
from worker.base import Worker
from utils.logging import setup_logger

logger = setup_logger()

NGINX_CONFIG_TEMPLATE = """
worker_processes 1;
daemon off; # Crucial for Popen to manage Nginx as a foreground process
pid {pid_file_path};
error_log {error_log_path};

events {{
    worker_connections 1024;
}}

http {{
    access_log {access_log_path};

    upstream backend {{
        server {proxy_target_host}:{proxy_target_port};
    }}

    server {{
        listen {nginx_listen_port};

        location / {{
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }}
    }}
}}
"""

class NginxWorker(Worker):
    """
    Nginx Worker，负责管理 Nginx 进程，实现流量负载均衡等功能
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.nginx_process: Optional[subprocess.Popen] = None
        
        self.nginx_executable = shutil.which('nginx')
        if not self.nginx_executable:
            logger.error("Nginx executable not found in PATH. NginxWorker will not function.")
            # self.running will remain False, start will effectively be a no-op
            return

        self.config_file_path = f"/tmp/nginx_worker_{self.id}.conf"
        self.pid_file_path = f"/tmp/nginx_worker_{self.id}.pid"
        self.access_log_path = f"/tmp/nginx_worker_{self.id}_access.log"
        self.error_log_path = f"/tmp/nginx_worker_{self.id}_error.log"

        self.nginx_listen_port = self.config.get('nginx_listen_port', 8080)
        self.proxy_target_host = self.config.get('proxy_target_host', 'localhost')
        self.proxy_target_port = self.config.get('proxy_target_port', 5000)
        
        self.status = 'stopped'

    def _generate_nginx_config(self) -> bool:
        if not self.nginx_executable:
            return False
        content = NGINX_CONFIG_TEMPLATE.format(
            pid_file_path=self.pid_file_path,
            error_log_path=self.error_log_path,
            access_log_path=self.access_log_path,
            nginx_listen_port=self.nginx_listen_port,
            proxy_target_host=self.proxy_target_host,
            proxy_target_port=self.proxy_target_port
        )
        try:
            with open(self.config_file_path, 'w') as f:
                f.write(content)
            logger.info(f"Generated Nginx config: {self.config_file_path}")
            return True
        except IOError as e:
            logger.error(f"Failed to write Nginx config file {self.config_file_path}: {e}")
            return False

    def _get_pid(self) -> Optional[int]:
        if not os.path.exists(self.pid_file_path):
            return None
        try:
            with open(self.pid_file_path, 'r') as f:
                return int(f.read().strip())
        except (IOError, ValueError) as e:
            logger.error(f"Failed to read or parse PID file {self.pid_file_path}: {e}")
            return None

    def _is_nginx_process_running_by_pid(self) -> bool:
        pid = self._get_pid()
        if not pid:
            return False
        try:
            os.kill(pid, 0) # Check if process exists
            return True
        except OSError:
            return False

    def _start_nginx_process(self):
        if not self.nginx_executable:
            logger.error("Cannot start Nginx: executable not found.")
            self.status = 'error'
            return

        if not self._generate_nginx_config():
            logger.error("Cannot start Nginx: failed to generate config.")
            self.status = 'error'
            return

        # Clean up old PID file if it exists and process is not running
        if os.path.exists(self.pid_file_path) and not self._is_nginx_process_running_by_pid():
            try:
                os.remove(self.pid_file_path)
            except OSError as e:
                logger.warning(f"Could not remove old PID file {self.pid_file_path}: {e}")
        
        cmd = [self.nginx_executable, '-c', self.config_file_path]
        try:
            logger.info(f"Starting Nginx with command: {' '.join(cmd)}")
            # Start Nginx in the foreground so Popen can manage it
            self.nginx_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, # Or subprocess.DEVNULL
                stderr=subprocess.PIPE  # Or subprocess.DEVNULL
            )
            # Give Nginx a moment to start and write its PID file
            time.sleep(1) 
            
            pid = self._get_pid()
            if pid and self._is_nginx_process_running_by_pid():
                logger.info(f"Nginx started successfully with PID {pid} (Popen PID {self.nginx_process.pid}). Listening on port {self.nginx_listen_port}.")
                self.status = 'running'
            else:
                logger.error(f"Nginx process started (Popen PID {self.nginx_process.pid}) but PID file {self.pid_file_path} not found or process not running by PID.")
                if self.nginx_process.poll() is None: # if Popen process is still running
                    self.nginx_process.terminate()
                    self.nginx_process.wait(timeout=5)
                self.status = 'error'

        except Exception as e:
            logger.error(f"Failed to start Nginx process: {e}")
            self.status = 'error'
            if self.nginx_process:
                self.nginx_process.kill() # Ensure it's killed if Popen started but other things failed

    def _stop_nginx_process(self):
        logger.info("Attempting to stop Nginx process...")
        nginx_pid = self._get_pid()

        if self.nginx_process and self.nginx_process.poll() is None:
            logger.info(f"Sending TERM signal to Nginx Popen process {self.nginx_process.pid}")
            self.nginx_process.terminate()
            try:
                self.nginx_process.wait(timeout=10)
                logger.info(f"Nginx Popen process {self.nginx_process.pid} terminated.")
            except subprocess.TimeoutExpired:
                logger.warning(f"Nginx Popen process {self.nginx_process.pid} did not terminate gracefully, killing.")
                self.nginx_process.kill()
        elif nginx_pid and self._is_nginx_process_running_by_pid():
            logger.info(f"Nginx Popen process not managed or already exited. Attempting to stop Nginx master (PID {nginx_pid}) via signal.")
            try:
                os.kill(nginx_pid, signal.SIGQUIT) # Graceful stop
                time.sleep(2) # Give it time to quit
                if self._is_nginx_process_running_by_pid(): # Check if still running
                    logger.warning(f"Nginx (PID {nginx_pid}) did not stop with SIGQUIT, sending SIGTERM.")
                    os.kill(nginx_pid, signal.SIGTERM)
                    time.sleep(2)
                    if self._is_nginx_process_running_by_pid():
                        logger.warning(f"Nginx (PID {nginx_pid}) did not stop with SIGTERM, sending SIGKILL.")
                        os.kill(nginx_pid, signal.SIGKILL)
                logger.info(f"Nginx process (PID {nginx_pid}) stopped via signal.")
            except OSError as e:
                logger.error(f"Error stopping Nginx (PID {nginx_pid}) via signal: {e}")
        else:
            logger.info("Nginx process not found or already stopped.")
        
        self.status = 'stopped'
        self._cleanup_files()

    def _cleanup_files(self):
        files_to_remove = [
            self.config_file_path, 
            self.pid_file_path,
            self.access_log_path,
            self.error_log_path
        ]
        for f_path in files_to_remove:
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    logger.info(f"Removed temporary file: {f_path}")
                except OSError as e:
                    logger.warning(f"Failed to remove temporary file {f_path}: {e}")
    
    def start(self):
        if not self.nginx_executable:
            logger.error("NginxWorker cannot start: Nginx executable not found.")
            self.running = False
            return

        if self.running:
            logger.warning(f"{self.__class__.__name__} {self.id} is already running or starting.")
            return
        
        logger.info(f"Starting {self.__class__.__name__} {self.id}")
        self.running = True
        self._start_nginx_process()

    def _run(self):
        pass

    def stop(self):
        if not self.running and self.status == 'stopped':
            logger.warning(f"{self.__class__.__name__} {self.id} is already stopped.")
            return

        logger.info(f"Stopping {self.__class__.__name__} {self.id}")
        self.running = False
        
        self._stop_nginx_process()
        
        logger.info(f"{self.__class__.__name__} {self.id} has been stopped.")

    def _check_config_changes(self, new_config: Dict[str, Any]) -> bool:
        if new_config.get('nginx_listen_port', self.nginx_listen_port) != self.nginx_listen_port:
            return True
        if new_config.get('proxy_target_host', self.proxy_target_host) != self.proxy_target_host:
            return True
        if new_config.get('proxy_target_port', self.proxy_target_port) != self.proxy_target_port:
            return True
        return False

    def update_config(self, config: Dict[str, Any]):
        if not self.nginx_executable:
            logger.error("Cannot update config: Nginx executable not found.")
            super().update_config(config)
            return

        logger.info(f"Updating Nginx config for worker {self.id}")
        config_changed = self._check_config_changes(config)
        
        super().update_config(config)

        self.nginx_listen_port = self.config.get('nginx_listen_port', self.nginx_listen_port)
        self.proxy_target_host = self.config.get('proxy_target_host', self.proxy_target_host)
        self.proxy_target_port = self.config.get('proxy_target_port', self.proxy_target_port)

        if config_changed:
            logger.info("Nginx configuration parameters changed.")
            if self.status == 'running':
                logger.info("Nginx is running, attempting to regenerate config and reload.")
                if self._generate_nginx_config():
                    pid = self._get_pid()
                    if pid and self._is_nginx_process_running_by_pid():
                        try:
                            logger.info(f"Sending SIGHUP to Nginx process PID {pid} to reload configuration.")
                            os.kill(pid, signal.SIGHUP)
                        except OSError as e:
                            logger.error(f"Failed to send SIGHUP to Nginx (PID {pid}): {e}. Consider restarting worker.")
                    else:
                        logger.warning("Nginx process not found by PID after config change. Reload skipped. Will apply on next start.")
                else:
                    logger.error("Failed to regenerate Nginx config for reload. Reload skipped.")
            else:
                logger.info("Nginx not running. Configuration will be applied on next start.")
        else:
            logger.info("Nginx configuration parameters unchanged. No reload needed.")
    
    def _get_resources(self) -> Dict[str, Any]:
        return {
            'status': self.status,
            'nginx_listen_port': self.nginx_listen_port,
            'proxy_target': f"{self.proxy_target_host}:{self.proxy_target_port}",
            'config_file': self.config_file_path if self.nginx_executable else "N/A",
            'pid_file': self.pid_file_path if self.nginx_executable else "N/A",
            'nginx_pid': self._get_pid(),
            'is_running_by_pid': self._is_nginx_process_running_by_pid()
        }
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if not self.nginx_executable:
             return {'success': False, 'error': 'Nginx not configured on this worker (executable not found).'}

        if not request.get('action'):
            return {'success': False, 'error': 'Missing action'}
        
        try:
            action = request.get('action')
            if action == 'status':
                return {
                    'success': True,
                    'status': self.status,
                    'details': self._get_resources()
                }
            elif action == 'reload':
                logger.info("Received 'reload' request for NginxWorker.")
                self.update_config(self.config)
                return {'success': True, 'message': 'Configuration reload process triggered (if changes detected or Nginx running).'}
            elif action == 'restart':
                logger.info("Received 'restart' request for NginxWorker.")
                self._stop_nginx_process()
                if self.running:
                     self._start_nginx_process()
                     if self.status == 'running':
                         return {'success': True, 'message': 'Nginx restarted successfully.'}
                     else:
                         return {'success': False, 'error': 'Nginx failed to restart.'}
                else:
                    return {'success': True, 'message': 'Nginx stopped as part of restart; worker is not set to run.'}
            else:
                return {'success': False, 'error': f'Unknown action: {action}'}
                
        except Exception as e:
            logger.error(f"Error handling Nginx request {action}: {e}")
            return {'success': False, 'error': str(e)}
