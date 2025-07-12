import pkg from 'discord.js';
const { REST, Routes } = pkg;
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import dotenv from 'dotenv';
dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const commands = [];
const commandsPath = path.join(__dirname, 'commands');
const commandFiles = fs.readdirSync(commandsPath).filter(f => f.endsWith('.js'));

for (const file of commandFiles) {
  const { data } = await import(`file://${path.join(commandsPath, file)}`);
  commands.push(data.toJSON());
}

const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_BOT_TOKEN);

(async () => {
  try {
    console.log('⏳ Refreshing application (/) commands...');
    await rest.put(
      Routes.applicationGuildCommands(
        process.env.DISCORD_APPLICATION_ID,
        process.env.DISCORD_GUILD_ID
      ),
      { body: commands }
    );
    console.log('✅ Commands reloaded.');
  } catch (error) {
    console.error(error);
  }
})();