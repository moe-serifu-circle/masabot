#!/usr/bin/env python

# contains support functions for the shell supervisor (for compatibility)
# should NOT be installed if masabot is installed as a pip program.

import subprocess
import os.path
import json
import sys


def get_sleep_cmd(seconds):
	if os.name == 'nt':
		# leave it to windows to not have a proper sleep command
		return 'ping -n ' + str(seconds) + ' 127.0.0.1 >nul'
	else:
		return 'sleep ' + str(seconds)


def cmd_end():
	if os.name == 'nt':
		return '&&'
	else:
		return ';'


def get_activation_command(virtualenv_dir=None):
	if virtualenv_dir is not None:
		while virtualenv_dir.endswith('/') or virtualenv_dir.endswith('\\'):
			virtualenv_dir = virtualenv_dir[:-1]
		if not os.path.exists(virtualenv_dir) or not os.path.isdir(virtualenv_dir):
			msg = "Virtual environment path '" + str(virtualenv_dir) + "' not found"
			raise ValueError(msg)
	else:
		if os.path.exists('venv') and os.path.isdir('venv'):
			virtualenv_dir = 'venv'
		elif os.path.exists('.venv') and os.path.isdir('.venv'):
			virtualenv_dir = '.venv'
		else:
			msg = "Virtual environment not found in '.venv' or 'venv';\nplease create one for masabot before executing"
			raise ValueError(msg)

	if os.name == 'nt':
		exec_dir = 'Scripts'
	else:
		bin_dir = os.path.join(virtualenv_dir, 'bin')
		scripts_dir = os.path.join(virtualenv_dir, 'Scripts')
		if os.path.exists(bin_dir) and os.path.isdir(bin_dir):
			exec_dir = 'bin'
		elif os.path.exists(scripts_dir) and os.path.isdir(scripts_dir):
			exec_dir = 'Scripts'
		else:
			msg = "Virtual environment not found in '" + virtualenv_dir + "/bin' or '" + virtualenv_dir + "/Scripts'.\n"
			msg += "Please ensure setup is correct."
			raise ValueError(msg)

	if os.name == 'nt':
		script_name = 'activate.bat'
	else:
		script_name = 'activate'

	full_path = os.path.join(virtualenv_dir, exec_dir, script_name)
	if os.name == 'nt':
		return full_path
	else:
		return '. ' + full_path


def run_venv_shell(exe, path=None):
	lines = []
	cmd = get_activation_command(path) + ' ' + cmd_end() + ' ' + exe + ' >' + os.path.join('ipc', 'temp')
	cmd += ' 2>&1'

	try:
		subprocess.check_output(cmd, shell=True, universal_newlines=True)
	except subprocess.CalledProcessError as e:
		with open(os.path.join('ipc', 'temp'), 'r') as fp:
			e.output = fp.read()
		os.remove(os.path.join('ipc', 'temp'))
		raise

	with open(os.path.join('ipc', 'temp'), 'r') as fp:
		for line in fp:
			lines.append(line.strip('\n'))

	os.remove(os.path.join('ipc', 'temp'))
	return lines


def deploy(is_redeploy=False, virtual_environment_path=None):
	installed = []
	if os.path.exists(os.path.join('ipc', 'installed-packages')):
		with open(os.path.join('ipc', 'installed-packages'), 'r') as fp:
			for line in fp:
				installed.append(line.strip())

	output_dict = {
		'action': "redeploy" if is_redeploy else "deploy"
	}

	try:
		required = run_venv_shell("python setup.py get_required_packages", path=virtual_environment_path)
	except subprocess.CalledProcessError:
		output_dict['success'] = False
		output_dict['message'] = "Checking required packages failed"
		output_dict['packages'] = []
		output_dict['check_package_success'] = False
		return output_dict

	output_dict['check_package_success'] = True
	output_dict['success'] = True
	output_dict['message'] = "All packages changes completed"

	install_count = 0
	install_fail_count = 0
	remove_count = 0
	remove_fail_count = 0

	package_statuses = {}

	for req in required:
		if req not in installed:
			install_count += 1
			try:
				run_venv_shell("pip install " + req, path=virtual_environment_path)
			except subprocess.CalledProcessError as e:
				install_fail_count += 1
				package_statuses[req] = {'success': False, 'action': "install", 'message': e.output}
			else:
				package_statuses[req] = {'success': True, 'action': "install", 'message': 'Installed successfully'}
				installed.append(req)

	new_installed = []
	for inst in installed:
		if inst not in required:
			remove_count += 1
			try:
				run_venv_shell("pip uninstall -y " + inst, path=virtual_environment_path)
			except subprocess.CalledProcessError as e:
				remove_fail_count += 1
				package_statuses[inst] = {'success': False, 'action': "uninstall", 'message': e.output}
				new_installed.append(inst)
			else:
				package_statuses[inst] = {'success': True, 'action': "uninstall", 'message': 'Uninstalled successfully'}
		else:
			new_installed.append(inst)
	installed = new_installed

	output_dict['packages'] = package_statuses

	if install_fail_count > 0:
		output_dict['success'] = False
		if remove_fail_count > 0:
			output_dict['message'] = "Some package installation(s) failed, and some package removal(s) failed."
		else:
			output_dict['message'] = "Some package installation(s) failed."
	elif remove_fail_count > 0:
		output_dict['message'] = "Some package removal(s) failed."
		output_dict['success'] = False

	with open(os.path.join('ipc', 'installed-packages'), 'w') as fp:
		for inst in installed:
			fp.write(inst + '\n')

	return output_dict


if __name__ == "__main__":
	if len(sys.argv) < 2:
		print("Need supervisor subcommand to execute", file=sys.stderr)
		sys.exit(1)
	if sys.argv[0] != 'supervisor/supervisor.py':
		print("Must execute supervisor module from within supervisor script", file=sys.stderr)
		sys.exit(2)

	if sys.argv[1] == 'redeploy':
		print("Running redeploy...")
		venv_dir = None
		if len(sys.argv) >= 3:
			venv_dir = sys.argv[2]
		output = deploy(is_redeploy=True, virtual_environment_path=venv_dir)
	elif sys.argv[1] == 'initial-deploy':
		print("Running deploy...")
		venv_dir = None
		if len(sys.argv) >= 3:
			venv_dir = sys.argv[2]
		output = deploy(virtual_environment_path=venv_dir)
	else:
		print("Unknown subcommand '" + sys.argv[1] + "'", file=sys.stderr)
		sys.exit(3)

	with open(os.path.join('ipc', 'status'), 'w') as status_file_fp:
		json.dump(output, status_file_fp)
