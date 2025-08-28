#ssh_connector.py
import wexpect
import time
import datetime
import sys

import config

def create_ssh_session(
        hostname,
        username,
        password,
        retries = config.SSH_CONNECT_RETRIES,
        base_delay = config.SSH_CONNECT_DELAY):
    """
    Create a single SSH session. Retry when failed or closed connection.
    """
    for attempt in range(1, retries + 1):
        now = datetime.datetime.now()
        today_tag = datetime.date.today().strftime('%Y%m%d')
        
        try:
            ssh_cmd = (
                f'ssh '
                f'-o BatchMode=no '
                f'-o ServerAliveInterval=30 '
                f'-o ServerAliveCountMax=3 '
                f'{username}@{hostname}'
            )
            # Create an SSH session using wexpect
            print(f'[SSH {now:%m/%d/%Y %H:%M:%S}] Connecting ({attempt}/{retries}) → {ssh_cmd}')
            ssh_session = wexpect.spawn(ssh_cmd, maxread=65535, timeout=config.SSH_EXPECT_TIMEOUT)

            i = ssh_session.expect([r"yes/no", rf"{username}@{hostname}'s password: ", config.SSH_PROMPT, wexpect.EOF, wexpect.TIMEOUT])
            if i == 0:
                ssh_session.sendline("yes")
                i = ssh_session.expect([rf"{username}@{hostname}'s password: ", config.SSH_PROMPT, wexpect.EOF, wexpect.TIMEOUT])
            if i == 1:
                ssh_session.sendline(password)
                ssh_session.expect(config.SSH_PROMPT)
            elif i == 2:
                pass
            else:
                with open(f"upsstatus_v4_{today_tag}.err", "a") as ferr:
                    ferr.write(f"[SSH {now:%d/%m/%Y %H:%M:%S}] : handshake failed (EOF/TIMEOUT)")
                raise RuntimeError("[SSH {now:%m/%d/%Y %H:%M:%S}] handshake failed (EOF/TIMEOUT)")

            ssh_session.sendline("") # match the prompt sync
            ssh_session.expect(config.SSH_PROMPT)
            print(f'[SSH {now:%m/%d/%Y %H:%M:%S}] Connected & prompt ready.')
            return ssh_session
        
        except Exception as e:
            delay = base_delay * (2 ** (attempt -1 ))
            print(f'[SSH {now:%m/%d/%Y %H:%M:%S}] Connect failed: {e} - retry in {delay}s', file=sys.stderr)
            with open(f"upsstatus_v4_{today_tag}.err", "a") as ferr:
                ferr.write(f"[ERR] {now:%d/%m/%Y %H:%M:%S} : SSH connection failed: {e} - retry in {delay}s")
                
            time.sleep(delay)

    # === when all reconnection attempts failed ===
    with open(f"upsstatus_v4_{today_tag}.err", "a") as ferr:
        ferr.write(f"[ERR] {now:%d/%m/%Y %H:%M:%S} : Exceeded SSH connection retries")
    raise RuntimeError(f'[SSH {now:%m/%d/%Y %H:%M:%S}] Exceeded SSH connection retries')


def is_session_alive(session):
    try:
        return (session is not None) and (not session.closed) and session.isalive()
    except Exception:
        return False

def ensure_prompt(session):
    session.sendline("")
    session.expect(config.SSH_PROMPT, timeout=config.SSH_EXPECT_TIMEOUT)

def execute_command(session, cmd, prompt=config.SSH_PROMPT, timeout=config.SSH_EXPECT_TIMEOUT):
    session.sendline(cmd)
    session.expect(prompt, timeout=timeout)
    return session.before
