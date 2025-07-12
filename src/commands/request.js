import { SlashCommandBuilder } from 'discord.js';

export const data = new SlashCommandBuilder()
  .setName('request')
  .setDescription('Start a reservation alert request');

export async function execute(interaction) {
  await interaction.reply({ content: 'Request feature coming soon!', ephemeral: true });
}
