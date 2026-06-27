#!/usr/bin/env python3
# CVPS Discord Bot — Made by @radoslavgeme
import discord, requests, os, json
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN","")
API = os.getenv("CVPS_API","http://localhost:7821")
ADMIN_TOKEN = os.getenv("CVPS_ADMIN_TOKEN","")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def api(method, endpoint, data=None, token=ADMIN_TOKEN):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{API}{endpoint}"
    if method=="GET": r = requests.get(url, headers=headers)
    elif method=="POST": r = requests.post(url, headers=headers, json=data)
    elif method=="DELETE": r = requests.delete(url, headers=headers)
    return r.json()

@bot.event
async def on_ready():
    await tree.sync()
    print(f"CVPS Bot online as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="CVPS | /help"))

@tree.command(name="help", description="Show all CVPS commands")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="CVPS Bot — Made by @radoslavgeme", color=0x00ffcc)
    embed.add_field(name="Container Commands", value="""
`/create` - Create a container
`/list` - List containers
`/start` - Start container
`/stop` - Stop container
`/restart` - Restart container
`/delete` - Delete container
`/info` - Container info
`/stats` - Container stats
""", inline=False)
    embed.add_field(name="Admin Commands", value="""
`/useradd` - Add user
`/userdel` - Delete user
`/users` - List users
`/logs` - View logs
`/status` - System status
""", inline=False)
    embed.set_footer(text="CVPS v1.0.0 — Made by @radoslavgeme")
    await interaction.response.send_message(embed=embed)

@tree.command(name="status", description="System status")
async def status_cmd(interaction: discord.Interaction):
    d = api("GET", "/system/status")
    embed = discord.Embed(title="CVPS System Status", color=0x00ff00)
    embed.add_field(name="Containers", value=f"{d.get('running',0)} running / {d.get('total',0)} total")
    embed.add_field(name="Users", value=d.get("users",0))
    embed.add_field(name="Host RAM", value=f"{d.get('host_ram_used',0)}MB / {d.get('host_ram_total',0)}MB")
    embed.add_field(name="Host CPU", value=f"{d.get('host_cpu',0):.1f}%")
    embed.add_field(name="Uptime", value=d.get("uptime","-"))
    embed.set_footer(text="Made by @radoslavgeme")
    await interaction.response.send_message(embed=embed)

@tree.command(name="list", description="List all containers")
async def list_cmd(interaction: discord.Interaction):
    d = api("GET", "/containers/list")
    if not d: await interaction.response.send_message("No containers."); return
    embed = discord.Embed(title="Containers", color=0x0099ff)
    for c in d:
        st = c.get("status","?")
        emoji = "🟢" if st=="running" else "🔴"
        embed.add_field(name=f"{emoji} {c['name']}", value=f"RAM: {c['ram']}MB | CPU: {c['cpus']} | Disk: {c['disk']}GB | IP: {c.get('ip','-')}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="create", description="Create a container")
@app_commands.describe(name="Container name", ram="RAM in MB", cpus="Number of CPUs", disk="Disk in GB")
async def create_cmd(interaction: discord.Interaction, name: str, ram: int, cpus: int, disk: int):
    await interaction.response.defer()
    d = api("POST", "/containers/create", {"name":name,"ram":ram,"cpus":cpus,"disk":disk})
    if "error" in d:
        await interaction.followup.send(f"❌ {d['error']}")
    else:
        embed = discord.Embed(title=f"✅ Container {name} Created", color=0x00ff00)
        embed.add_field(name="IP", value=d.get("ip","pending"))
        embed.add_field(name="RAM", value=f"{ram}MB")
        embed.add_field(name="CPUs", value=cpus)
        embed.add_field(name="Disk", value=f"{disk}GB")
        embed.add_field(name="SSH", value=f"ssh root@{d.get('ip','<ip>')}")
        await interaction.followup.send(embed=embed)

@tree.command(name="start", description="Start a container")
@app_commands.describe(name="Container name")
async def start_cmd(interaction: discord.Interaction, name: str):
    d = api("POST", f"/containers/{name}/start")
    await interaction.response.send_message(f"{'✅' if 'message' in d else '❌'} {d.get('message',d.get('error',''))}")

@tree.command(name="stop", description="Stop a container")
@app_commands.describe(name="Container name")
async def stop_cmd(interaction: discord.Interaction, name: str):
    d = api("POST", f"/containers/{name}/stop")
    await interaction.response.send_message(f"{'✅' if 'message' in d else '❌'} {d.get('message',d.get('error',''))}")

@tree.command(name="restart", description="Restart a container")
@app_commands.describe(name="Container name")
async def restart_cmd(interaction: discord.Interaction, name: str):
    api("POST", f"/containers/{name}/stop")
    import time; time.sleep(1)
    d = api("POST", f"/containers/{name}/start")
    await interaction.response.send_message(f"✅ {name} restarted")

@tree.command(name="delete", description="Delete a container (admin only)")
@app_commands.describe(name="Container name")
async def delete_cmd(interaction: discord.Interaction, name: str):
    d = api("DELETE", f"/containers/{name}")
    await interaction.response.send_message(f"{'✅' if 'message' in d else '❌'} {d.get('message',d.get('error',''))}")

@tree.command(name="info", description="Container info")
@app_commands.describe(name="Container name")
async def info_cmd(interaction: discord.Interaction, name: str):
    d = api("GET", f"/containers/{name}/info")
    if "error" in d: await interaction.response.send_message(f"❌ {d['error']}"); return
    embed = discord.Embed(title=f"Container: {name}", color=0x0099ff)
    embed.add_field(name="Status", value=d.get("status","-"))
    embed.add_field(name="IP", value=d.get("ip","-"))
    embed.add_field(name="RAM", value=f"{d['ram']}MB")
    embed.add_field(name="CPUs", value=d['cpus'])
    embed.add_field(name="Disk", value=f"{d['disk']}GB")
    embed.add_field(name="Owner", value=d.get("owner","-"))
    await interaction.response.send_message(embed=embed)

@tree.command(name="useradd", description="Add a user (admin)")
@app_commands.describe(username="Username", password="Password")
async def useradd_cmd(interaction: discord.Interaction, username: str, password: str):
    d = api("POST", "/admin/users", {"username":username,"password":password})
    await interaction.response.send_message(f"{'✅' if 'message' in d else '❌'} {d.get('message',d.get('error',''))}", ephemeral=True)

@tree.command(name="userdel", description="Delete a user (admin)")
@app_commands.describe(username="Username")
async def userdel_cmd(interaction: discord.Interaction, username: str):
    d = api("DELETE", f"/admin/users/{username}")
    await interaction.response.send_message(f"{'✅' if 'message' in d else '❌'} {d.get('message',d.get('error',''))}")

@tree.command(name="users", description="List all users (admin)")
async def users_cmd(interaction: discord.Interaction):
    d = api("GET", "/admin/users")
    embed = discord.Embed(title="Users", color=0x9900ff)
    for u in d:
        embed.add_field(name=u["username"], value=f"Role: {u['role']} | Containers: {len(u.get('containers',[]))}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="logs", description="View system logs (admin)")
async def logs_cmd(interaction: discord.Interaction):
    d = api("GET", "/admin/logs")
    logs = d.get("logs",[])[-20:]
    text = "\n".join(logs) or "No logs."
    await interaction.response.send_message(f"```\n{text}\n```")

if __name__ == "__main__":
    if not TOKEN: print("Set DISCORD_TOKEN in /opt/cvps/.env"); exit(1)
    bot.run(TOKEN)
