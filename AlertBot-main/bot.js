// src/bot.js
import { Client, Collection, GatewayIntentBits, ActionRowBuilder, StringSelectMenuBuilder, ModalBuilder, TextInputBuilder, TextInputStyle, InteractionResponseFlags } from 'discord.js';
import dotenv from 'dotenv';
import { loginToDisney } from './disneyAuth.js';
import { fetchRestaurantData } from './disneyRestaurants.js';

dotenv.config();

const client = new Client({
  intents: [GatewayIntentBits.Guilds]
});

client.commands = new Collection();

// --- your slash command registration / deploy-commands.js remains unchanged ---

client.once('ready', async () => {
  console.log(`Logged in as ${client.user.tag}`);
  await loginToDisney(); // make sure this handles cookie refresh internally
});

// Handle the initial /request command
client.on('interactionCreate', async interaction => {
  if (interaction.isChatInputCommand() && interaction.commandName === 'request') {
    // show a 4-field modal
    const modal = new ModalBuilder()
      .setCustomId('diningModal')
      .setTitle('Set up your alert');

    // Resort/Park select
    const locationMenu = new StringSelectMenuBuilder()
      .setCustomId('locationSelect')
      .setPlaceholder('Choose Resort or Park')
      .addOptions([
        // these should come dynamically; here's a placeholder
        { label: 'Magic Kingdom', value: 'MK' },
        { label: 'EPCOT',       value: 'EP' }
      ]);
    const locRow = new ActionRowBuilder().addComponents(locationMenu);

    // Restaurant menu (will be replaced after locationSelect)
    const restMenu = new StringSelectMenuBuilder()
      .setCustomId('restaurantSelect')
      .setPlaceholder('First choose a location above');
    const restRow = new ActionRowBuilder().addComponents(restMenu);

    // Date picker
    const dateInput = new TextInputBuilder()
      .setCustomId('dateInput')
      .setLabel('Date (YYYY-MM-DD)')
      .setStyle(TextInputStyle.Short)
      .setPlaceholder('e.g. 2025-08-01');
    const dateRow = new ActionRowBuilder().addComponents(dateInput);

    // Meal period select
    const mealMenu = new StringSelectMenuBuilder()
      .setCustomId('mealSelect')
      .setPlaceholder('Breakfast / Lunch / Dinner')
      .addOptions([
        { label: 'Breakfast', value: 'breakfast' },
        { label: 'Lunch',     value: 'lunch'     },
        { label: 'Dinner',    value: 'dinner'    }
      ]);
    const mealRow = new ActionRowBuilder().addComponents(mealMenu);

    modal.addComponents(locRow, restRow, dateRow, mealRow);
    await interaction.showModal(modal);
  }

  // Handle the modal submit
  if (interaction.isModalSubmit() && interaction.customId === 'diningModal') {
    const [location, restaurant, date, meal] = [
      interaction.fields.getTextInputValue('locationSelect'),
      interaction.fields.getTextInputValue('restaurantSelect'),
      interaction.fields.getTextInputValue('dateInput'),
      interaction.fields.getTextInputValue('mealSelect')
    ];
    // store their choices and kick off your watcher...
    await interaction.reply({
      content: `✅ Alert set!\n• Location: **${location}**\n• Restaurant: **${restaurant}**\n• Date: **${date}**\n• Meal: **${meal}**`,
      flags: InteractionResponseFlags.Ephemeral
    });
  }
});

client.login(process.env.DISCORD_TOKEN);
