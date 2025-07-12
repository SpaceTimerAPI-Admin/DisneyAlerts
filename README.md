# WDW Dining Alert Bot

## Setup

1. Copy `.env.example` to `.env` and fill in:
   - `DISCORD_APPLICATION_ID`
   - `DISCORD_BOT_TOKEN`
   - `DISCORD_GUILD_ID`
   - `DISNEY_EMAIL`
   - `DISNEY_PASSWORD`

2. Install dependencies:
   ```
   npm install
   npx playwright install
   ```

3. Deploy slash commands:
   ```
   npm run deploy-commands
   ```

4. Start the bot:
   ```
   npm start
   ```

## Project Structure

- `src/bot.js` - Discord client setup & command handling
- `src/deploy-commands.js` - Registers slash commands
- `src/commands/request.js` - `/request` command stub
