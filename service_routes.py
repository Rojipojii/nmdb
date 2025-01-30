from flask import Blueprint, jsonify, Flask,render_template, flash
import subprocess
import datetime
import os

service_routes = Blueprint('service_routes', __name__)

@service_routes.route('/svcrestart', methods=['POST', 'GET'])
def svcrestart():
    try:
        # Restart the service using systemctl
        subprocess.run(['/usr/bin/sudo', '/usr/bin/systemctl', 'restart', 'flaskapp.service'], check=True)
        flash ('Webserver restarted. Please login again','success')
        # return (f"Webserver restarted.")
        return render_template('index.html')
    except subprocess.CalledProcessError:
       flash ('Webserver restarted. Please login again','success')
       return render_template('index.html')

@service_routes.route('/backup', methods=['GET'])

def backup():
    BACKUP_DIR = 'backups'
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_file = f"{BACKUP_DIR}/backup_{timestamp}.sql"
        command = f"/usr/bin/mysqldump -u nmdbuse -pXtDs7r8e1sKNjD nmdb > {backup_file}"

        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            return jsonify({"error": stderr.decode('utf-8')}), 500
        # flash (f"Database Backup Created")
        return jsonify({"message": "DB Backup created successfully", "backup_file": backup_file})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500