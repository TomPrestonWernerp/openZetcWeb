"""Exercise deployment ordering without starting or replacing real containers."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("failure", ["", "build", "infrastructure"])
def test_deploy_preserves_infrastructure_and_stops_on_failure(tmp_path, failure):
    source = Path(os.environ["DEPLOY_SCRIPT_UNDER_TEST"])
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(source, scripts / "deploy-prod.sh")
    (scripts / "prepare-prod-env.sh").write_text("#!/bin/bash\nexit 0\n")
    (scripts / "prepare-prod-env.sh").chmod(0o755)
    nginx = tmp_path / "docker/nginx/nginx"
    certs = nginx / "cert"
    certs.mkdir(parents=True)
    for path in [
        nginx / "nginx.conf",
        nginx / "default.conf",
        certs / "scs1776824001002_.zjshjkj.com_server.crt",
        certs / "scs1776824001002_.zjshjkj.com_server.key",
    ]:
        path.touch()
    docker = tmp_path / "docker-mock-bin"
    docker.mkdir()
    executable = docker / "docker"
    executable.write_text(
        "#!/bin/bash\n"
        'echo "$*" >> "$COMMAND_LOG"\n'
        'if [[ "$FAILURE" == build && "$*" == *" build "* ]]; then exit 17; fi\n'
        'if [[ "$FAILURE" == infrastructure && "$*" == *" --no-recreate "* ]]; then exit 18; fi\n'
        'if [[ "$*" == *" python -c "* ]]; then echo same-hash; fi\n'
        'if [[ "$*" == *" python -" ]]; then cat >/dev/null; fi\n'
    )
    executable.chmod(0o755)
    log = tmp_path / "commands.log"
    result = subprocess.run(
        ["bash", str(scripts / "deploy-prod.sh")],
        env={**os.environ, "PATH": f"{docker}:{os.environ['PATH']}",
             "COMMAND_LOG": str(log), "FAILURE": failure},
        capture_output=True,
        text=True,
    )
    commands = log.read_text().splitlines()
    recreates = [command for command in commands if "--force-recreate" in command]
    if failure:
        assert result.returncode == (17 if failure == "build" else 18)
        assert not recreates
        if failure == "build":
            assert not any(" up " in command for command in commands)
    else:
        assert result.returncode == 0, result.stderr
        assert len(recreates) == 1
        assert "--no-deps" in recreates[0]
        assert recreates[0].endswith(" api worker web")
        infrastructure = next(command for command in commands if "--no-recreate" in command)
        assert "--wait" in infrastructure
        assert commands.index(infrastructure) < commands.index(recreates[0])
