import pkg from 'discord.js';
const { Client, Collection, GatewayIntentBits } = pkg;
import dotenv from 'dotenv';
dotenv.config();

const client = new Client({ intents: [GatewayIntentBits.Guilds] });
client.commands = new Collection();

// Load command handlers
import { requestCommand } from './commands/request.js';
client.commands.set(requestCommand.data.name, requestCommand);

client.on('ready', () => {
  console.log(`✅ Logged in as ${client.user.tag}`);
});

client.on('interactionCreate', async interaction => {
  if (!interaction.isChatInputCommand()) return;
  const command = client.commands.get(interaction.commandName);
  if (!command) return;
  try {
    await command.execute(interaction);
  } catch (err) {
    console.error(err);
    await interaction.reply({ content: 'An error occurred.', ephemeral: true });
  }
});

client.login(process.env.DISCORD_BOT_TOKEN);