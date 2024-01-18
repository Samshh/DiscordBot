import os
import datetime
from pytz import timezone
from dotenv import load_dotenv
import json
import discord
from discord.ext import commands, tasks
from discord import Interaction

UTC8 = timezone('Asia/Singapore')

# IMPORTANT: API SECURITY KEY
load_dotenv()
TOKEN = os.getenv('TOKEN')
BOT_CREATOR_ID = int(os.getenv('BOT_CREATOR_ID'))
PREFIX = os.getenv('PREFIX')
MOD_MAIL_SETTINGS_FILE = 'mod_mail_settings.json'

client = commands.Bot(
    command_prefix=PREFIX, 
    intents=discord.Intents.all(), 
    help_command=None
)

#load
def timestamp():
    return datetime.datetime.now(UTC8).strftime("%m-%d %H:%M")

def date():
    return datetime.datetime.now(UTC8).strftime("%m-%d")

def save_mod_mail_settings():
    with open(MOD_MAIL_SETTINGS_FILE, 'w') as file:
        json.dump(mod_mail_settings, file)

def load_mod_mail_settings():
    try:
        with open(MOD_MAIL_SETTINGS_FILE, 'r') as file:
            data = json.load(file)
            return data if data else {}
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        return {}

#checks
def has_admin_permissions(ctx):
    return ctx.author.guild_permissions.administrator

def has_mod_permissions(ctx):
    required_permissions = discord.Permissions(kick_members=True, ban_members=True)
    return ctx.author.guild_permissions >= required_permissions

def is_bot_owner(ctx):
    return ctx.author.id == BOT_CREATOR_ID

#on_ready
@client.event
async def on_ready():
    global mod_mail_settings
    mod_mail_settings = load_mod_mail_settings()
    await client.tree.sync()
    await update_presence()
    print('Bot is ready!')
    if PREFIX:
        print(f'Loaded prefix: {PREFIX}')
    else:
        print('No prefix loaded.')

#reset mod mail
@client.command()
@commands.check(has_admin_permissions)
async def reset(ctx):
    global mod_mail_settings
    mod_mail_settings = {} 
    save_mod_mail_settings()

    await ctx.send("`Mod mail settings have been reset.`", delete_after=10)

@client.event
async def on_member_join(member):
    print(f'{member} has joined the server {member.guild.name}!')
    await update_presence()

@client.event
async def on_guild_join(guild):
    print(f'Joined {guild.name}!')
    await update_presence()

@client.event
async def on_guild_remove(guild):
    print(f'Left {guild.name}!')
    await update_presence()

#loop for update presence
@tasks.loop(minutes=5)
async def update_presence():
    total_member_count = 0
    for guild in client.guilds:
        if guild.member_count:
            total_member_count += guild.member_count
    activity = discord.Activity(name=f"over {total_member_count} users!", type=discord.ActivityType.watching)
    await client.change_presence(activity=activity)

    print('Bot presence updated!')

#on_message
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    await client.process_commands(message)

    if message.author.id == BOT_CREATOR_ID:
        return
    if isinstance(message.channel, discord.DMChannel):
        bot_owner = await client.fetch_user(BOT_CREATOR_ID)
        content = f"Received DM from {message.author} (ID: {message.author.id})\nContent: {message.content}"
        if message.attachments:
            content += "\nAttachments:"
            for attachment in message.attachments:
                content += f"\n{attachment.url}"
        await bot_owner.send(content)

#purge command
@client.command()
@commands.check(has_mod_permissions or has_admin_permissions)
async def purge(ctx, amount: int):
    try:
        if 1 <= amount <= 20:
            await ctx.channel.purge(limit=amount + 1)
            await ctx.send(f'`Deleted {amount} messages.`', delete_after=10)
        else:
            await ctx.send('`Please provide a number between 1 and 20 for the amount of messages to delete.`', delete_after=10)
    except discord.errors.Forbidden:
        await ctx.send("`You do not have permission to delete messages in this channel.`", delete_after=10)
    except Exception as e:
        await ctx.send(f'`An error occurred: {e}`', delete_after=10)

@client.command()
async def hello(ctx):
    await ctx.send(mention_author=True, content=f'`Hello` {ctx.author.mention}!')

#update presence
@client.command()
@commands.check(is_bot_owner)
async def presence(ctx):
    await update_presence()
    await ctx.send('`Presence updated!`', delete_after=10)

#ticket system
@client.tree.command(
    name='ticket', 
    description='Create a ticket channel'
)
async def ticket(interaction, reason: str):
    mod_mail_channel_id = mod_mail_settings.get('mod_mail_channel_id')
    if interaction.user.id == interaction.user.id:
        mod_mail_channel = interaction.guild.get_channel(mod_mail_channel_id)
        if mod_mail_channel:
            category = mod_mail_channel.category
            existing_ticket = mod_mail_settings.get(interaction.user.id)
            if existing_ticket:
                existing_channel = interaction.guild.get_channel(existing_ticket[0])
                await interaction.response.send_message(
                    f'`You already have an open ticket: {existing_channel.name}`', ephemeral=True, delete_after=5
                )
                return
            new_channel = await interaction.guild.create_text_channel(
                name=f'{interaction.user.name}-{date()}-ticket',
                category=category
            )
            mod_mail_settings[interaction.user.id] = (new_channel.id, new_channel.name)
            save_mod_mail_settings()
            await set_ticket_channel_permissions(new_channel, interaction.user)
            welcome_message = (
                f'`Welcome to your ticket channel,` {interaction.user.mention}\n'
                f'`Please wait for staff to assist you. If you no longer need help, use {PREFIX}close.`\n'
                f'`Reason for ticket:` {reason}'
            )
            await new_channel.send(welcome_message)
            user_dm_message = (
                f'`Thanks for using the ticket system! abusing this system will lead to a ban`\n'
            )
            await interaction.user.send(user_dm_message)
            await interaction.response.send_message(
                f'`Ticket channel created: `{new_channel.name}', ephemeral=True, delete_after=5
            )
        else:
            await interaction.response.send_message("`Mod mail channel not found. Please contact an admin/mod`", ephemeral=True, delete_after=5)
    else:
        return

async def set_ticket_channel_permissions(channel, user):
    await channel.set_permissions(user, read_messages=True, send_messages=True)
    await channel.set_permissions(channel.guild.default_role, read_messages=False, send_messages=False)

#close ticket
@client.command()
async def close(ctx):
    if ctx.channel.name.endswith('-ticket'):
        await ctx.channel.set_permissions(ctx.author, overwrite=None)
        user_ticket_info = mod_mail_settings.pop(ctx.author.id, None)
        if user_ticket_info:
            await ctx.send(f'`Ticket channel closed by` {ctx.author.mention} `Staff will no longer receive messages in this channel.`')
            save_mod_mail_settings()
            user_dm_message = (
                f'`Your ticket ({user_ticket_info[1]}) has been closed.`\n'
                f'`If you need assistance again, use /ticket.`'
            )
            await ctx.author.send(user_dm_message)
        else:
            await ctx.send(f'`Ticket channel closed by` {ctx.author.mention} `Staff will no longer receive messages in this channel.`')
            await ctx.channel.delete()
    else:
        return

#delete ticket
@client.command()
@commands.check(has_admin_permissions)
async def delete(ctx):
    if ctx.channel.name.endswith('-ticket'):
        await ctx.channel.delete()
    else:
        return

#owner command
@client.tree.command(
    name='send_dm', 
    description='Send a DM to a user'
)
@commands.check(is_bot_owner)
async def send_dm(interaction: Interaction, user_id: str, message: str):
    if interaction.user.id != BOT_CREATOR_ID:
        await interaction.response.send_message("`You do not have permission to use this command.`", ephemeral=True, delete_after=5)
        return
    try:
        target_user = await client.fetch_user(int(user_id))
        await target_user.send(message)
        await interaction.response.send_message(f"Message sent to {target_user}: {message}", ephemeral=True)
    except discord.errors.NotFound:
        await interaction.response.send_message("`User not found.`", ephemeral=True, delete_after=5)

# youtube link
@client.tree.command(name='chillin', description='ghibli vibes')
async def meiplechill(interaction: Interaction):
    await interaction.response.send_message('https://youtu.be/7c4rlVOFFDk')

# latency check command
@client.tree.command(
    name='ping', 
    description='how slow is meiple?'
)
async def ping(interaction: Interaction):
    bot_latency = round(client.latency * 1000)
    if bot_latency > 100:
        await interaction.response.send_message(f'`Kinda slow af: {bot_latency}ms`')
    elif bot_latency < 50:
        await interaction.response.send_message(f'`Fast af: {bot_latency}ms`')

#ban commands
@client.tree.command(
    name='ban', 
    description='Ban a member'
)
@commands.check(has_mod_permissions or has_admin_permissions)
async def ban(interaction: Interaction, member: discord.Member, reason: str = None):
    if interaction.user.top_role.position > member.top_role.position:
        await member.ban(reason=reason)
        await interaction.response.send_message(f'`{member} has been banned.`')
    else:
        await interaction.response.send_message("`You do not have permission to ban this member.`", ephemeral=True, delete_after=5)

@client.tree.command(name='banid', description='ban a user by ID')
@commands.check(has_mod_permissions or has_admin_permissions)
async def banid(interaction: Interaction, user_id: str, reason: str = None):
    banned_user = await client.fetch_user(int(user_id))
    try:
        await interaction.guild.ban(banned_user, reason=reason)
        await interaction.response.send_message(f'`{banned_user} (ID: {user_id}) has been banned.`')
        print(f'{timestamp()} | {banned_user} (ID: {user_id}) has been banned by {interaction.user} in {interaction.guild} for {reason}')
    except discord.NotFound:
        await interaction.response.send_message(f'`User with ID {user_id} not found.`', ephemeral=True, delete_after=5)
    except discord.Forbidden:
        await interaction.response.send_message("`You do not have permission to ban members.`", ephemeral=True, delete_after=5)

#kick command
@client.tree.command(
    name='kick', 
    description='Kick a member'
)
@commands.check(has_mod_permissions or has_admin_permissions)
async def kick(interaction: Interaction, member: discord.Member, reason: str = None):
    if interaction.user.top_role.position > member.top_role.position:
        await member.kick(reason=reason)
        await interaction.response.send_message(f'`{member} has been kicked.`')
        print(f'{timestamp()} | {member} has been kicked by {interaction.user} in {interaction.guild} for {reason}')
    else:
        await interaction.response.send_message("`You do not have permission to kick this member.`", ephemeral=True, delete_after=5)

#member info
@client.tree.command(
    name='member', 
    description='Get member info'
)
@commands.check(has_mod_permissions or has_admin_permissions)
async def member(interaction: Interaction, member: discord.Member):
    if interaction.user.top_role.position > member.top_role.position:
        await interaction.response.send_message(
            f'`Name: {member.name}\nID: {member.id}\nCreated at: {member.created_at}\nJoined at: {member.joined_at}\nAvatar:`{member.avatar}', ephemeral=True)
    else:
        await interaction.response.send_message("`You do not have permission to view information about this member.`", ephemeral=True, delete_after=5)

#unban command
@client.tree.command(
    name='unban', 
    description='Unban a user by ID'
)
@commands.check(has_mod_permissions or has_admin_permissions)
async def unban(interaction: Interaction, user_id: str, reason: str = None):
    banned_user = await client.fetch_user(int(user_id))
    try:
        await interaction.guild.unban(banned_user, reason=reason)
        await interaction.response.send_message(f'`{banned_user} (ID: {user_id}) has been unbanned.`')
        print(f'{timestamp()} | {banned_user} (ID: {user_id}) has been unbanned by {interaction.user} in {interaction.guild} for {reason}')
    except discord.NotFound:
        await interaction.response.send_message(f'`User with ID {user_id} not found or not banned.`', ephemeral=True, delete_after=5)
    except discord.Forbidden:
        await interaction.response.send_message("`You do not have permission to unban members.`", ephemeral=True, delete_after=5)

#avatar command
@client.tree.command(
    name='avatar', 
    description='get member avatar'
)
async def avatar(interaction: Interaction, member: discord.Member):
    await interaction.response.send_message(f'{member.avatar}', ephemeral=True)

#announce command
@client.tree.command(
    name='announce', 
    description='announce on a channel'
)
@commands.check(has_mod_permissions or has_admin_permissions)
async def announce(interaction: Interaction, channel_reference: str, message: str):
  try:
    if channel_reference.startswith("<#") and channel_reference.endswith(">"):
      channel_id = int(channel_reference[2:-1])
      target_channel = client.get_channel(channel_id)
    else:
      target_channel = discord.utils.get(interaction.guild.channels, name=channel_reference)
    if target_channel:
      await target_channel.send(f'{message}')
      await interaction.response.send_message(
          f'`Announcement sent in {target_channel.name}` {message}')
    else:
      await interaction.response.send_message(
          f'`Channel {channel_reference} not found. Available channels: {", ".join(c.name for c in interaction.guild.channels)}`',
          ephemeral=True, delete_after=5)
  except discord.errors.Forbidden:
    await interaction.response.send_message(
        "`You do not have permission to send messages in that channel.`", ephemeral=True, delete_after=5)
  except Exception as e:
    await interaction.response.send_message(f'`An error occurred: {e}`', ephemeral=True, delete_after=5)

#mod mail setup
@client.tree.command(
    name='set_mod_mail', 
    description='mod_mail_setup'
)
@commands.check(has_admin_permissions)
async def set_mod_mail(interaction: Interaction, channel_name: str, category_reference: str):
    try:
        if category_reference.startswith("<#") and category_reference.endswith(">"):
            category_id = int(category_reference[2:-1])
            target_category = discord.utils.get(interaction.guild.categories, id=category_id)
        else:
            target_category = discord.utils.get(interaction.guild.categories, name=category_reference)

        if target_category:
            new_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=target_category
            )
            await new_channel.set_permissions(interaction.guild.default_role, read_messages=True, send_messages=False)
            mod_mail_settings['mod_mail_channel_id'] = new_channel.id

            save_mod_mail_settings()

            await interaction.response.send_message(
                f'`Mod mail category set to {target_category.name}`\n'
                f'`Mod mail channel created: {new_channel.name}`'
            )
            welcome_message = f"`Welcome to {new_channel.name} channel, use /ticket`"
            await new_channel.send(welcome_message)

        else:
            await interaction.response.send_message(
                f'`Category {category_reference} not found. Available categories: {", ".join(c.name for c in interaction.guild.categories)}`'
            )
    except discord.errors.Forbidden:
        await interaction.response.send_message(
            '`You do not have permission to create channels in that category.`', ephemeral=True, delete_after=5
        )
    except Exception as e:
        await interaction.response.send_message(f'`An error occurred: {e}`', ephemeral=True, delete_after=5)

#error handling
@client.event
async def on_command_error(ctx, error):
    print(f'Error: {error}')

client.run(TOKEN)