#discord bot V1 by Aiden Chang and James Glassford
#written June 2021, rewritten December 2022



import discord
from discord.ext import commands, tasks
from discord.ext.commands import CommandNotFound
from discord.utils import get
import time
import asyncio
import re
import boto3
from datetime import datetime

server_id = 0
server_afk_channel = 0
server_silly_role = 0


bot = commands.Bot(command_prefix = "Jarvis, ", description = "Bot is online!\n", intents = discord.Intents().all())

@tasks.loop(hours = 24)
async def check_date(ctx):
    date = datetime.now()


#for when a command is entered that doesn't exist - we don't really need it to do anything
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandNotFound):
        print("uh oh!")

#runs everytime the bot turns on
@bot.event
async def on_ready():
    print("We have logged in as {0.user}".format(bot))


#For testing purposes - anything in this function is temporary
@bot.command()
async def test(ctx):
    server_id = ctx.guild.id
    server_afk_channel = ctx.guild.afk_channel
    for role in ctx.guild.roles:
        await ctx.send(role)
        print(role)


#Call and response from the bot, to see if it's working
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")
    
#Silly goose vote
@bot.command()
async def vote(ctx):
    if ctx.author == bot.user:
        return

    member = ctx.author
    #needs person who called vote to be in a voice channel
    if member.voice is not None:
        pass
        channel = member.voice.channel
        #grabs the name, discord ID and member data of the accused user
        accusedName = ctx.message.mentions[0].display_name
        accusedID = ctx.message.mentions[0].id
        accused = ctx.guild.get_member(accusedID)
        #needs accused to exist, and to be in the same voice channel as the user who called the vote
        if accused is not None and accused.voice.channel == channel:
            #needs 5 people to start a vote - this should probably be editable by admins
            members = channel.members
            if len(members) >= 5:
                await ctx.send(
                    f"{member.display_name} is accusing {accusedName} of being a silly goose. You have 60 seconds to vote, the accused must be found guilty by more than half of the voters."
                )
                #calls the poll if all required parameters are met
                await poll(ctx, accused)
            else:
                await ctx.send("There needs to be a minimum of 5 members in your current voice channel to use this command.")

        else:
            await ctx.send("Make sure you typed the correct used ID and that they are in the same voice channel as you.")

    else:
        await ctx.send("You are not in a channel!")



@bot.command()
async def poll(ctx, member:discord.member.Member):
    total_members = len(ctx.author.voice.channel.members)
    #ensures that 50% of the vote is needed for guilty verdict
    guilty_number = total_members/2
    reactions = ['👍', '👎']
    embed = discord.Embed(title = f"Is {member.display_name} being a silly goose?", color = 3553599)
    react_message = await ctx.channel.send(embed)
    #adds reactions users vote with to the message
    for reaction in reactions:
        await react_message.add_reaction(reaction)
    message = await ctx.channel.fetch_message(react_message.id)
    embed.set_footer(text = "Poll ID: {}".format(react_message.id))
    #starts a timer; we want the vote to last for a maximum of 60 seconds
    start_time = time.time()
    guilty = False
    while time.time() < start_time + 60:
        #these are initialized to -1 because the bot added one of each reaction
        yes_votes = -1
        no_votes = -1
        msg = await ctx.fetch_message(react_message.id)
        cache_msg = discord.utils.get(bot.cached_messages, id = react_message.id)
        for r in msg.reactions:
            if str(r) == '👍':
                yes_votes +=r.count
            elif str(r) == '👎':
                no_votes+=r.count
        if(yes_votes > guilty_number):
            await ctx.send("Guilty! sending to the pond.")
            guilty = True
            await travel(ctx, member)
            break
        elif no_votes >= total_members - 1:
            await ctx.send(f"In a shocking turn of events, it seems that {ctx.author.display_name} was the one being a silly goose all along!")
            guilty = True
            await travel(ctx, ctx.author)
            break
        if(guilty == False):
            await ctx.send(f"{member.display_name} has been cleared of all sillyness.")


async def travel(ctx, member: discord.member.Member):
    pond = bot.get_channel(server_afk_channel)
    original_channel = bot.get_channel(member.voice.channel.id)
    await member.move_to(pond)
    #goes through list of channels and locks member out of each one
    for channel in ctx.guild.channels:
        await channel.set_permissions(member, connect = False)
        if(member.channel != pond):
            await member.move_to(pond)
    #after 60 seconds, unlock each channel and move member back to original channel
    time.sleep(60)
    await member.move_to(original_channel)
    for channel in ctx.guild.channels:
        await channel.set_permissions(member, connect = True)
    

def dynamo_init():
    dynamodb = boto3.resource('dynamodb', region_name = 'us-east-2')

#if user is not in the dynamodb database, adds user
def dynamo_addUser(userID, dynamodb = None):
    if not dynamodb:
        dynamo_init()
    table = dynamodb.Table(f"{server_id}")
    response = table.put_item(
        Item = {
            "userID": userID,
            "info": {
                "counter": 0,
            }
        }
    )

#returns the guilty counter for the given member
def dynamo_getCount(userID, dynamodb = None):
    try:
        if not dynamodb:
            dynamo_init()
        table = dynamodb.Table(f'{server_id}')

        try:
            response = table.get_item(Key = {'userID': userID})
        except ClientError as e:
            print(e.response['Error']['Message'])
        else:
            temp = response['Item']
            return int(temp['info']['counter'])    
    except KeyError:
        return 'error'


#updates associated values based on case
def dynamo_updateUser(userID, case, dynamodb = None):
    if not dynamodb:
        dynamo_init()
    
    table = dynamodb.Table(f'{server_id}')
    geese = dynamo_getCount(userID)

    #if case is 0, we are trying to reset the user's guilty counter
    if case == 0:
        value = 0
    elif case == 1:
        value = 1
    response = table.update_item(
        Key = {
            'userID': userID
        },
        UpdateExpression = "set info.counter=:c",
        ExpressionAttributeValues = {
            ':c': value
        },
        ReturnValues = "UPDATED_NEW"
    )
    return response

#set to run on the first of every month, resets the guilty counter of all members in the server
def dynamo_monthly_reset(ctx):
    for m in ctx.guild.members:
        id_response = dynamo_getCount(m.id, 0)
        if id_response == 'error':
            dynamo_addUser(m.id, 0)
        else:
            dynamo_updateUser(m.id, 0)

#finds the user with the highest guilty counter
def dynamo_monthlyWinner(ctx):
    leader_count = 0
    leader_name = discord.member.Membersilliest_goose = get()

#awards the monthly winner with a special role
@bot.command()
async def update_role(ctx):
    await ctx.send("")


token = 'ODUyMzk2OTAyNDY4NDE5NjA0.GU_HH8.IBL377k6tewFWNMpsa1QqSaUMxMoivLv5A2gvs'
bot.run(token)