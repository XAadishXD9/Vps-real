# bot.py
import os
import subprocess
import asyncio
import random
import discord
from discord.ext import tasks, commands
from discord import app_commands

# ---------- Config ----------
TOKEN = ''  # <-- Replace with your token
OWNER_ID = 1405778722732376176
ADMINS_FILE = "admins.txt"
DATABASE_FILE = "database.txt"
RAM_LIMIT = '2g'
SERVER_LIMIT = 12
PUBLIC_IP = '138.68.79.95'  # used for port-add response (keep or change)

# Docker images for reinstall/deploy
UBUNTU_IMAGE = "ubuntu-22.04-with-tmate"
DEBIAN_IMAGE = "debian-with-tmate"

intents = discord.Intents.default()
intents.messages = False
intents.message_content = False

bot = commands.Bot(command_prefix='/', intents=intents)
# ----------------------------

# ---------- Helpers ----------
def is_owner(user_id: int) -> bool:
    return int(user_id) == int(OWNER_ID)

def is_admin(user_id: int) -> bool:
    if is_owner(user_id):
        return True
    if not os.path.exists(ADMINS_FILE):
        return False
    with open(ADMINS_FILE, "r") as f:
        admins = [line.strip() for line in f.readlines() if line.strip()]
    return str(user_id) in admins

def add_admin_to_file(user_id: int):
    if not os.path.exists(ADMINS_FILE):
        open(ADMINS_FILE, "w").close()
    with open(ADMINS_FILE, "a") as f:
        f.write(f"{user_id}\n")

def remove_admin_from_file(user_id: int):
    if not os.path.exists(ADMINS_FILE):
        return
    with open(ADMINS_FILE, "r") as f:
        admins = [line.strip() for line in f.readlines() if line.strip()]
    admins = [a for a in admins if a != str(user_id)]
    with open(ADMINS_FILE, "w") as f:
        if admins:
            f.write("\n".join(admins) + "\n")

def add_to_database(user: str, container_id: str, ssh_command: str, os_type: str = "ubuntu"):
    # store format: user|container_id|ssh_command|os
    if not os.path.exists(DATABASE_FILE):
        open(DATABASE_FILE, "w").close()
    with open(DATABASE_FILE, 'a') as f:
        f.write(f"{user}|{container_id}|{ssh_command}|{os_type}\n")

def remove_from_database(container_id: str):
    if not os.path.exists(DATABASE_FILE):
        return
    with open(DATABASE_FILE, 'r') as f:
        lines = [line.rstrip("\n") for line in f.readlines() if line.strip()]
    with open(DATABASE_FILE, 'w') as f:
        for line in lines:
            if container_id not in line.split("|")[1]:
                f.write(line + "\n")

def get_user_servers(user: str):
    if not os.path.exists(DATABASE_FILE):
        return []
    servers = []
    with open(DATABASE_FILE, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("|")
            # Accept old 3-field format or new 4-field
            if len(parts) >= 3:
                owner = parts[0]
                container_id = parts[1]
                ssh_command = parts[2]
                os_type = parts[3] if len(parts) >= 4 else "ubuntu"
                if owner == user:
                    servers.append({
                        "user": owner,
                        "container_id": container_id,
                        "ssh_command": ssh_command,
                        "os": os_type
                    })
    return servers

def get_all_servers():
    if not os.path.exists(DATABASE_FILE):
        return []
    servers = []
    with open(DATABASE_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                owner = parts[0]
                container_id = parts[1]
                ssh_command = parts[2]
                os_type = parts[3] if len(parts) >= 4 else "ubuntu"
                servers.append({
                    "user": owner,
                    "container_id": container_id,
                    "ssh_command": ssh_command,
                    "os": os_type
                })
    return servers

def get_container_info_by_id(container_id: str):
    # return dict or None
    all_s = get_all_servers()
    for s in all_s:
        if s["container_id"] == container_id:
            return s
    return None

def count_user_servers(user: str) -> int:
    return len(get_user_servers(user))

def generate_random_port():
    return random.randint(1025, 65535)

# ---------- Async helpers for reading tmate output ----------
async def capture_ssh_session_line(process):
    # reads stdout line by line until "ssh session:" or similar appears
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        try:
            text = line.decode('utf-8').strip()
        except:
            text = str(line).strip()
        # tmate prints something like "ssh session: ssh ..." or "ssh: ..."
        if "ssh session" in text.lower() or "ssh:" in text.lower():
            # attempt to extract an ssh command portion
            # return the whole line to be safe
            return text
    return None

async def capture_output(process, keyword: str):
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        try:
            text = line.decode('utf-8').strip()
        except:
            text = str(line).strip()
        if keyword in text:
            return text
    return None

# ---------- Events & Tasks ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    change_status.start()
    print(f"Bot ready. Logged in as {bot.user} (ID: {bot.user.id})")

@tasks.loop(seconds=5)
async def change_status():
    try:
        if os.path.exists(DATABASE_FILE):
            with open(DATABASE_FILE, 'r') as f:
                lines = [l for l in f.readlines() if l.strip()]
                instance_count = len(lines)
        else:
            instance_count = 0
        status = f"with {instance_count} Cloud Instances"
        await bot.change_presence(activity=discord.Game(name=status))
    except Exception as e:
        print("Failed to update status:", e)

# ---------- Admin Commands ----------
@bot.tree.command(name="add_admin", description="Adds a new admin (Owner only)")
@app_commands.describe(user="The user to make admin")
async def add_admin(interaction: discord.Interaction, user: discord.User):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ You are not authorized to use this command.", color=0xff0000))
        return
    add_admin_to_file(user.id)
    await interaction.response.send_message(embed=discord.Embed(description=f"✅ {user.mention} has been added as an admin.", color=0x00ff00))

@bot.tree.command(name="remove_admin", description="Removes an admin (Owner only)")
@app_commands.describe(user="The admin user to remove")
async def remove_admin(interaction: discord.Interaction, user: discord.User):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ You are not authorized to use this command.", color=0xff0000))
        return
    if not os.path.exists(ADMINS_FILE):
        await interaction.response.send_message(embed=discord.Embed(description="ℹ️ No admins file found.", color=0xff0000))
        return
    if str(user.id) not in open(ADMINS_FILE).read():
        await interaction.response.send_message(embed=discord.Embed(description=f"⚠️ {user.mention} is not an admin.", color=0xffcc00))
        return
    remove_admin_from_file(user.id)
    await interaction.response.send_message(embed=discord.Embed(description=f"✅ {user.mention} has been removed from the admin list.", color=0x00ff00))

@bot.tree.command(name="list_admin", description="Lists all current admins (Owner only)")
async def list_admin(interaction: discord.Interaction):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ You are not authorized to use this command.", color=0xff0000))
        return
    if not os.path.exists(ADMINS_FILE):
        await interaction.response.send_message(embed=discord.Embed(description="ℹ️ No admins found.", color=0x00ff00))
        return
    with open(ADMINS_FILE, "r") as f:
        admin_ids = [line.strip() for line in f.readlines() if line.strip()]
    if not admin_ids:
        await interaction.response.send_message(embed=discord.Embed(description="ℹ️ No admins have been added yet.", color=0x00ff00))
        return
    admin_list = "\n".join([f"<@{aid}>" for aid in admin_ids])
    embed = discord.Embed(title="👑 Admin List", description=admin_list, color=0x00ff00)
    await interaction.response.send_message(embed=embed)

# ---------- VPS Listing for Owner/Admin ----------
@bot.tree.command(name="vps_list", description="Shows all VPS instances (Owner/Admin only)")
async def vps_list(interaction: discord.Interaction):
    user_id = interaction.user.id
    if not is_admin(user_id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ You are not authorized to use this command.", color=0xff0000))
        return
    servers = get_all_servers()
    if not servers:
        await interaction.response.send_message(embed=discord.Embed(description="ℹ️ There are currently no active VPS instances.", color=0x00ff00))
        return
    embed = discord.Embed(title="💻 All Active VPS Instances", color=0x00ff00)
    for s in servers:
        owner = s["user"]
        cid = s["container_id"]
        ssh = s["ssh_command"]
        os_type = s.get("os", "ubuntu")
        embed.add_field(name=f"👤 {owner} — `{cid}`", value=f"**OS:** {os_type}\n**SSH:** `{ssh}`", inline=False)
    await interaction.response.send_message(embed=embed)

# ---------- Port Forwarding ----------
@bot.tree.command(name="port-add", description="Adds a port forwarding rule")
@app_commands.describe(container_name="The name of the container", container_port="The port in the container")
async def port_add(interaction: discord.Interaction, container_name: str, container_port: int):
    await interaction.response.send_message(embed=discord.Embed(description="Setting up port forwarding. This might take a moment...", color=0x00ff00))
    public_port = generate_random_port()
    command = f"ssh -o StrictHostKeyChecking=no -R {public_port}:localhost:{container_port} serveo.net -N -f"
    try:
        # Run the command inside the container (detached)
        await asyncio.create_subprocess_exec(
            "docker", "exec", container_name, "bash", "-c", command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await interaction.followup.send(embed=discord.Embed(description=f"Port added successfully. Your service is hosted on {PUBLIC_IP}:{public_port}.", color=0x00ff00))
    except Exception as e:
        await interaction.followup.send(embed=discord.Embed(description=f"An unexpected error occurred: {e}", color=0xff0000))

@bot.tree.command(name="port-http", description="Forward HTTP traffic to your container")
@app_commands.describe(container_name="The name of your container", container_port="The port inside the container to forward")
async def port_forward_website(interaction: discord.Interaction, container_name: str, container_port: int):
    try:
        exec_cmd = await asyncio.create_subprocess_exec(
            "docker", "exec", container_name, "ssh", "-o", "StrictHostKeyChecking=no", "-R", f"80:localhost:{container_port}", "serveo.net",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        url_line = await capture_output(exec_cmd, "Forwarding HTTP traffic from")
        if url_line:
            # extract URL last token
            url = url_line.split(" ")[-1]
            await interaction.response.send_message(embed=discord.Embed(description=f"Website forwarded successfully. Your website is accessible at {url}.", color=0x00ff00))
        else:
            await interaction.response.send_message(embed=discord.Embed(description="Failed to capture forwarding URL.", color=0xff0000))
    except subprocess.CalledProcessError as e:
        await interaction.response.send_message(embed=discord.Embed(description=f"Error executing website forwarding: {e}", color=0xff0000))

# ---------- Deploy Commands ----------
@bot.tree.command(name="deploy-ubuntu", description="Creates a new Instance with Ubuntu 22.04")
async def deploy_ubuntu(interaction: discord.Interaction):
    await create_server_task(interaction, os_type="ubuntu")

@bot.tree.command(name="deploy-debian", description="Creates a new Instance with Debian 12")
async def deploy_debian(interaction: discord.Interaction):
    await create_server_task(interaction, os_type="debian")

# create_server_task supports both OS types
async def create_server_task(interaction: discord.Interaction, os_type: str = "ubuntu"):
    await interaction.response.send_message(embed=discord.Embed(description="Creating Instance, This takes a few seconds.", color=0x00ff00))
    user = str(interaction.user)
    if count_user_servers(user) >= SERVER_LIMIT:
        await interaction.followup.send(embed=discord.Embed(description="```Error: Instance Limit-reached```", color=0xff0000))
        return

    image = UBUNTU_IMAGE if os_type == "ubuntu" else DEBIAN_IMAGE

    try:
        container_id = subprocess.check_output([
            "docker", "run", "-itd", "--privileged", "--cap-add=ALL", image
        ]).strip().decode('utf-8')
    except subprocess.CalledProcessError as e:
        await interaction.followup.send(embed=discord.Embed(description=f"Error creating Docker container: {e}", color=0xff0000))
        return

    try:
        exec_cmd = await asyncio.create_subprocess_exec("docker", "exec", container_id, "tmate", "-F",
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except Exception as e:
        await interaction.followup.send(embed=discord.Embed(description=f"Error executing tmate in Docker container: {e}", color=0xff0000))
        subprocess.run(["docker", "kill", container_id])
        subprocess.run(["docker", "rm", container_id])
        return

    ssh_session_line = await capture_ssh_session_line(exec_cmd)
    if ssh_session_line:
        add_to_database(user, container_id, ssh_session_line, os_type)
        try:
            await interaction.user.send(embed=discord.Embed(description=f"### Successfully created Instance\nSSH Session Command: ```{ssh_session_line}```\nOS: {os_type.capitalize()}", color=0x00ff00))
        except:
            # DM might be closed; still acknowledge
            pass
        await interaction.followup.send(embed=discord.Embed(description="Instance created successfully. Check your DMs for details.", color=0x00ff00))
    else:
        await interaction.followup.send(embed=discord.Embed(description="Something went wrong or the Instance is taking longer than expected. If this problem continues, Contact Support.", color=0xff0000))
        subprocess.run(["docker", "kill", container_id])
        subprocess.run(["docker", "rm", container_id])

# ---------- Basic instance actions that users can call for their OWN containers ----------
@bot.tree.command(name="list", description="Lists all your Instances")
async def list_servers(interaction: discord.Interaction):
    user = str(interaction.user)
    servers = get_user_servers(user)
    if servers:
        embed = discord.Embed(title="Your Instances", color=0x00ff00)
        for server in servers:
            cid = server["container_id"]
            ssh = server["ssh_command"]
            os_type = server.get("os", "ubuntu")
            embed.add_field(name=f"`{cid}` (OS: {os_type})", value=f"SSH: `{ssh}`", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(embed=discord.Embed(description="You have no servers.", color=0xff0000))

@bot.tree.command(name="remove", description="Removes an Instance")
@app_commands.describe(container_name="The name/ssh-command of your Instance")
async def remove_server(interaction: discord.Interaction, container_name: str):
    user = str(interaction.user)
    # allow owner/admin to remove any, else user only their own
    target_info = get_container_info_by_id(container_name)
    if not target_info:
        await interaction.response.send_message(embed=discord.Embed(description="No Instance found for that container id.", color=0xff0000))
        return

    if not (is_admin(interaction.user.id) or target_info["user"] == user):
        await interaction.response.send_message(embed=discord.Embed(description="❌ You are not authorized to remove this instance.", color=0xff0000))
        return

    try:
        subprocess.run(["docker", "stop", container_name], check=False)
        subprocess.run(["docker", "rm", "-f", container_name], check=False)
        remove_from_database(container_name)
        await interaction.response.send_message(embed=discord.Embed(description=f"Instance '{container_name}' removed successfully.", color=0x00ff00))
    except Exception as e:
        await interaction.response.send_message(embed=discord.Embed(description=f"Error removing instance: {e}", color=0xff0000))

@bot.tree.command(name="regen-ssh", description="Generates a new SSH session for your instance")
@app_commands.describe(container_name="The name/ssh-command of your Instance")
async def regen_ssh(interaction: discord.Interaction, container_name: str):
    user = str(interaction.user)
    target_info = get_container_info_by_id(container_name)
    if not target_info:
        await interaction.response.send_message(embed=discord.Embed(description="No instance found for that container id.", color=0xff0000))
        return
    # allow only owner/admin or owner of instance
    if not (is_admin(interaction.user.id) or target_info["user"] == user):
        await interaction.response.send_message(embed=discord.Embed(description="❌ You are not authorized to regenerate SSH for this instance.", color=0xff0000))
        return

    try:
        exec_cmd = await asyncio.create_subprocess_exec("docker", "exec", container_name, "tmate", "-F",
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except Exception as e:
        await interaction.response.send_message(embed=discord.Embed(description=f"Error executing tmate in Docker container: {e}", color=0xff0000))
        return

    ssh_session_line = await capture_ssh_session_line(exec_cmd)
    if ssh_session_line:
        # update database entry
        # remove old, add new with same owner and os
        owner = target_info["user"]
        os_type = target_info.get("os", "ubuntu")
        remove_from_database(container_name)
        add_to_database(owner, container_name, ssh_session_line, os_type)
        try:
            await interaction.user.send(embed=discord.Embed(description=f"### New SSH Session Command: ```{ssh_session_line}```", color=0x00ff00))
        except:
            pass
        await interaction.response.send_message(embed=discord.Embed(description="New SSH session generated. Check your DMs for details.", color=0x00ff00))
    else:
        await interaction.response.send_message(embed=discord.Embed(description="Failed to generate new SSH session.", color=0xff0000))

# ---------- /manage command (unified) ----------
@bot.tree.command(name="manage", description="Manage a VPS instance with one command")
@app_commands.describe(
    container_id="The ID of the container you want to manage",
    action="What do you want to do? (start, stop, restart, reinstall, gen-ssh, install)"
)
async def manage(interaction: discord.Interaction, container_id: str, action: str):
    """
    Access policy:
    - Owner/Admin can manage any container.
    - Regular users can manage only their own containers.
    """
    action = action.lower().strip()
    valid_actions = ["start", "stop", "restart", "reinstall", "gen-ssh", "install"]
    if action not in valid_actions:
        await interaction.response.send_message(embed=discord.Embed(description=f"❌ Invalid action.\nUse one of: `{', '.join(valid_actions)}`", color=0xff0000))
        return

    caller = str(interaction.user)
    target_info = get_container_info_by_id(container_id)
    # If not tracked in DB, still allow admins/owner to act but warn users
    if not target_info:
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(embed=discord.Embed(description="❌ This container is not tracked in the database. Only owner/admins can operate untracked containers.", color=0xff0000))
            return
        else:
            # create minimal info for admin operations
            target_info = {"user": "unknown", "container_id": container_id, "ssh_command": "", "os": "ubuntu"}

    # permission check: owner/admin OR owner-of-instance
    if not (is_admin(interaction.user.id) or target_info["user"] == caller):
        await interaction.response.send_message(embed=discord.Embed(description="❌ You are not authorized to manage this instance.", color=0xff0000))
        return

    # Helper to ensure container exists
    def container_exists(cid: str):
        try:
            subprocess.run(["docker", "inspect", cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    # --- start ---
    if action == "start":
        try:
            subprocess.run(["docker", "start", container_id], check=True)
            await interaction.response.send_message(embed=discord.Embed(description=f"✅ Container `{container_id}` started successfully.", color=0x00ff00))
        except subprocess.CalledProcessError:
            await interaction.response.send_message(embed=discord.Embed(description=f"❌ Failed to start container `{container_id}`.", color=0xff0000))
        return

    # --- stop ---
    if action == "stop":
        try:
            subprocess.run(["docker", "stop", container_id], check=True)
            await interaction.response.send_message(embed=discord.Embed(description=f"🛑 Container `{container_id}` stopped successfully.", color=0x00ff00))
        except subprocess.CalledProcessError:
            await interaction.response.send_message(embed=discord.Embed(description=f"❌ Failed to stop container `{container_id}`.", color=0xff0000))
        return

    # --- restart ---
    if action == "restart":
        try:
            subprocess.run(["docker", "restart", container_id], check=True)
            await interaction.response.send_message(embed=discord.Embed(description=f"🔁 Container `{container_id}` restarted successfully.", color=0x00ff00))
        except subprocess.CalledProcessError:
            await interaction.response.send_message(embed=discord.Embed(description=f"❌ Failed to restart container `{container_id}`.", color=0xff0000))
        return

    # --- reinstall ---
    if action == "reinstall":
        os_type = target_info.get("os", "ubuntu")
        image = UBUNTU_IMAGE if os_type == "ubuntu" else DEBIAN_IMAGE
        await interaction.response.send_message(embed=discord.Embed(description=f"🔄 Reinstalling `{container_id}` with {os_type.capitalize()} image. This may take a minute...", color=0x00ff00))
        try:
            # remove old container (force)
            subprocess.run(["docker", "rm", "-f", container_id], check=False)
            # create new container with the same image
            new_container_id = subprocess.check_output([
                "docker", "run", "-itd", "--privileged", "--cap-add=ALL", image
            ]).strip().decode('utf-8')
            # start tmate in new container to produce ssh string
            exec_cmd = await asyncio.create_subprocess_exec("docker", "exec", new_container_id, "tmate", "-F",
                                                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            ssh_session_line = await capture_ssh_session_line(exec_cmd)
            if ssh_session_line:
                # update database: remove old entry, add new
                owner = target_info["user"]
                remove_from_database(container_id)
                add_to_database(owner, new_container_id, ssh_session_line, os_type)
                try:
                    await interaction.user.send(embed=discord.Embed(description=f"🔄 Reinstalled container.\n**New SSH:** ```{ssh_session_line}```\nOS: {os_type.capitalize()}", color=0x00ff00))
                except:
                    pass
                await interaction.response.send_message(embed=discord.Embed(description=f"✅ Reinstallation complete. New container id: `{new_container_id}`. Check your DMs for SSH details.", color=0x00ff00))
            else:
                await interaction.response.send_message(embed=discord.Embed(description=f"⚠️ Reinstalled but failed to generate SSH session for new container.", color=0xffcc00))
        except subprocess.CalledProcessError as e:
            await interaction.response.send_message(embed=discord.Embed(description=f"❌ Reinstallation failed: {e}", color=0xff0000))
        return

    # --- gen-ssh ---
    if action == "gen-ssh":
        await interaction.response.send_message(embed=discord.Embed(description=f"🔑 Generating new SSH session for `{container_id}`...", color=0x00ff00))
        try:
            exec_cmd = await asyncio.create_subprocess_exec("docker", "exec", container_id, "tmate", "-F",
                                                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            ssh_session_line = await capture_ssh_session_line(exec_cmd)
            if ssh_session_line:
                # update database entry with new ssh command (keep os and owner)
                owner = target_info["user"]
                os_type = target_info.get("os", "ubuntu")
                remove_from_database(container_id)
                add_to_database(owner, container_id, ssh_session_line, os_type)
                try:
                    await interaction.user.send(embed=discord.Embed(description=f"🔑 New SSH session:\n```{ssh_session_line}```", color=0x00ff00))
                except:
                    pass
                await interaction.response.send_message(embed=discord.Embed(description="✅ New SSH session generated. Check your DMs.", color=0x00ff00))
            else:
                await interaction.response.send_message(embed=discord.Embed(description=f"❌ Failed to generate SSH session for `{container_id}`.", color=0xff0000))
        except Exception as e:
            await interaction.response.send_message(embed=discord.Embed(description=f"⚠️ Error generating SSH: {e}", color=0xff0000))
        return

    # --- install packages ---
    if action == "install":
        # packages list per your request
        packages = [
            "tmate", "neofetch", "screen", "wget", "curl", "htop", "nano", "vim",
            "openssh-server", "sudo", "ufw", "git", "docker.io", "systemd", "systemd-sysv"
        ]
        await interaction.response.send_message(embed=discord.Embed(description=f"⚙️ Installing packages in `{container_id}`... This may take a few minutes.", color=0x00ff00))
        try:
            if not container_exists(container_id):
                await interaction.followup.send(embed=discord.Embed(description=f"❌ Container `{container_id}` does not exist.", color=0xff0000))
                return
            install_cmd = ["docker", "exec", container_id, "bash", "-c", f"apt update -y && apt install -y {' '.join(packages)}"]
            process = subprocess.run(install_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if process.returncode == 0:
                await interaction.followup.send(embed=discord.Embed(description=f"✅ Packages installed successfully in `{container_id}`.", color=0x00ff00))
            else:
                # include limited stderr for debugging
                err = process.stderr or process.stdout
                snippet = err[:1500] if err else "No output"
                await interaction.followup.send(embed=discord.Embed(description=f"❌ Installation failed:\n```\n{snippet}\n```", color=0xff0000))
        except Exception as e:
            await interaction.followup.send(embed=discord.Embed(description=f"⚠️ Unexpected error: {e}", color=0xff0000))
        return

# ---------- Utility commands ----------
@bot.tree.command(name="ping", description="Check the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", description=f"Latency: {latency}ms", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="Shows the help message")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Help", color=0x00ff00)
    embed.add_field(name="/deploy-ubuntu", value="Creates a new Instance with Ubuntu 22.04.", inline=False)
    embed.add_field(name="/deploy-debian", value="Creates a new Instance with Debian 12.", inline=False)
    embed.add_field(name="/remove <container_id>", value="Removes a server (owner/admin can remove any).", inline=False)
    embed.add_field(name="/start <container_id>", value="Start a server (use /manage for unified control).", inline=False)
    embed.add_field(name="/stop <container_id>", value="Stop a server (use /manage for unified control).", inline=False)
    embed.add_field(name="/regen-ssh <container_id>", value="Regenerates SSH credentials for your instance.", inline=False)
    embed.add_field(name="/restart <container_id>", value="Restart a server (use /manage).", inline=False)
    embed.add_field(name="/list", value="List your servers.", inline=False)
    embed.add_field(name="/vps_list", value="List all servers (owner/admin only).", inline=False)
    embed.add_field(name="/manage <container_id> <action>", value="Manage container. Actions: start, stop, restart, reinstall, gen-ssh, install", inline=False)
    embed.add_field(name="/port-add", value="Forward port using serveo.", inline=False)
    embed.add_field(name="/port-http", value="Forward HTTP using serveo.", inline=False)
    embed.add_field(name="/add_admin, /remove_admin, /list_admin", value="Owner-only admin management.", inline=False)
    await interaction.response.send_message(embed=embed)

# ---------- Start the bot ----------
if __name__ == "__main__":
    bot.run(TOKEN)
