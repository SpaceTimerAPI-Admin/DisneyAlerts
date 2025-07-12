import { SlashCommandBuilder } from 'discord.js';

export const requestCommand = {
  data: new SlashCommandBuilder()
    .setName('request')
    .setDescription('Set up a dining availability alert')
    .addStringOption(option =>
      option.setName('resort')
        .setDescription('Choose your resort or park')
        .setRequired(true))
    .addStringOption(option =>
      option.setName('restaurant')
        .setDescription('Choose a restaurant at that location')
        .setRequired(true))
    .addStringOption(option =>
      option.setName('date')
        .setDescription('Pick a date (YYYY-MM-DD)')
        .setRequired(true))
    .addStringOption(option =>
      option.setName('meal')
        .setDescription('Breakfast, Lunch, or Dinner')
        .setRequired(true)),
  async execute(interaction) {
    // Implementation placeholder
    await interaction.reply({ content: 'Request feature coming soon!', ephemeral: true });
  },
};