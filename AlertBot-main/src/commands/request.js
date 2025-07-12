import pkg from 'discord.js';
const { SlashCommandBuilder } = pkg;

export const data = new SlashCommandBuilder()
    .setName('request')
    .setDescription('Initiate a Disney dining alert request');
