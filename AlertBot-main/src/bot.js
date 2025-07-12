// src/bot.js
import pkg from 'discord.js';
const {
  Client,
  Collection,
  GatewayIntentBits,
  ActionRowBuilder,
  StringStringSelectMenuBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  InteractionResponseFlags
} = pkg;
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import dotenv from 'dotenv';
dotenv.config();

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages]
});

// derive __dirname in ESM
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// load commands
client.commands = new Collection();
const commandsPath = path.join(__dirname, 'commands');
for (const file of fs.readdirSync(commandsPath).filter(f => f.endsWith('.js'))) {
  const { data, execute } = await import(path.join(commandsPath, file));
  client.commands.set(data.name, { data, execute });
}

client.once('ready', () => {
  console.log(`✅ Logged in as ${client.user.tag}`);
});

client.on('interactionCreate', async interaction => {
  if (interaction.isChatInputCommand()) {
    const cmd = client.commands.get(interaction.commandName);
    if (!cmd) return;
    try {
      await cmd.execute(interaction);
    } catch (err) {
      console.error(err);
      await interaction.reply({
        content: '❌ There was an error executing that command.',
        ephemeral: true
      });
    }
  }
  // your select‐menu & modal handlers remain here…
});

client.login(process.env.DISCORD_TOKEN);
