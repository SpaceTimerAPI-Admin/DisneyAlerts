console.log('🐭 Starting DisneyDiningAlertBot…');
console.log('🔑 Token is', !!process.env.DISCORD_BOT_TOKEN);
client.login(process.env.DISCORD_BOT_TOKEN);
console.log('🚀 client.login() returned');


import pkg from 'discord.js';
import { fileURLToPath } from 'url';
import path from 'path';
import dotenv from 'dotenv';
dotenv.config();

const { Client, Collection, GatewayIntentBits, ActionRowBuilder,
        StringSelectMenuBuilder, ModalBuilder, TextInputBuilder,
        TextInputStyle, InteractionResponseFlags } = pkg;

// derive __dirname in ES module
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const client = new Client({ intents: [GatewayIntentBits.Guilds] });
client.commands = new Collection();

const commandsPath = path.join(__dirname, 'commands');
// ... (rest of your bot.js logic) ...

client.login(process.env.DISCORD_BOT_TOKEN);
