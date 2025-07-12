import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timedelta
import sqlite3
from typing import Dict, List, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DisneyAPI:
    """Handles Disney API interactions"""
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session = None
        self.access_token = None
        self.base_url = "https://disneyworld.disney.go.com"
        
    async def login(self):
        """Authenticate with Disney API"""
        self.session = aiohttp.ClientSession()
        
        # Disney login flow - this is simplified and may need adjustment
        login_url = f"{self.base_url}/authentication/login"
        
        login_data = {
            "loginValue": self.username,
            "password": self.password
        }
        
        try:
            async with self.session.post(login_url, json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data.get('access_token')
                    logger.info("Successfully logged into Disney API")
                    return True
                else:
                    logger.error(f"Login failed: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def get_locations(self) -> List[Dict]:
        """Get available dining locations (parks and resorts) from Disney API"""
        if not self.session or not self.access_token:
            await self.login()
        
        # Disney API endpoint for locations - this needs to be the actual endpoint
        locations_url = f"{self.base_url}/api/wdw/dining/locations"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        try:
            async with self.session.get(locations_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    # Parse the locations data - structure depends on Disney's API response
                    locations = []
                    
                    # This structure will depend on Disney's actual API response
                    # Common structure might be:
                    if 'destinations' in data:
                        for destination in data['destinations']:
                            locations.append({
                                'id': destination.get('id'),
                                'name': destination.get('name'),
                                'type': destination.get('type')  # 'park' or 'resort'
                            })
                    elif 'locations' in data:
                        for location in data['locations']:
                            locations.append({
                                'id': location.get('id'),
                                'name': location.get('name'),
                                'type': location.get('facilityType')
                            })
                    
                    logger.info(f"Retrieved {len(locations)} locations from Disney API")
                    return locations
                else:
                    logger.error(f"Failed to fetch locations: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching locations: {e}")
            return []
    
    async def get_restaurants(self, location_id: str) -> List[Dict]:
        """Get restaurants for a specific location from Disney API"""
        if not self.session or not self.access_token:
            await self.login()
        
        # Disney API endpoint for restaurants at a specific location
        restaurants_url = f"{self.base_url}/api/wdw/dining/restaurants"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        params = {
            "location": location_id,
            "filters": "dining"  # Only get dining locations
        }
        
        try:
            async with self.session.get(restaurants_url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    restaurants = []
                    
                    # Parse restaurant data - structure depends on Disney's API response
                    # Common structures might be:
                    if 'restaurants' in data:
                        for restaurant in data['restaurants']:
                            restaurants.append({
                                'id': restaurant.get('id'),
                                'name': restaurant.get('name'),
                                'location_id': location_id,
                                'cuisine_type': restaurant.get('cuisineType'),
                                'meal_periods': restaurant.get('mealPeriods', []),
                                'accepts_reservations': restaurant.get('acceptsReservations', False)
                            })
                    elif 'facilities' in data:
                        for facility in data['facilities']:
                            if facility.get('type') == 'restaurant':
                                restaurants.append({
                                    'id': facility.get('id'),
                                    'name': facility.get('name'),
                                    'location_id': location_id,
                                    'cuisine_type': facility.get('cuisineType'),
                                    'meal_periods': facility.get('availableMealPeriods', []),
                                    'accepts_reservations': facility.get('reservationRequired', False)
                                })
                    
                    # Filter only restaurants that accept reservations
                    reservation_restaurants = [r for r in restaurants if r['accepts_reservations']]
                    
                    logger.info(f"Retrieved {len(reservation_restaurants)} restaurants for location {location_id}")
                    return reservation_restaurants
                else:
                    logger.error(f"Failed to fetch restaurants for location {location_id}: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching restaurants for location {location_id}: {e}")
            return []
    
    async def check_availability(self, restaurant_id: str, party_size: int, 
                               date: str, meal_period: str) -> List[Dict]:
        """Check dining availability for specific parameters"""
        if not self.session or not self.access_token:
            await self.login()
        
        # This would make actual API calls to check availability
        # Sample implementation structure
        availability_url = f"{self.base_url}/dining/availability"
        
        params = {
            "restaurant": restaurant_id,
            "partySize": party_size,
            "date": date,
            "mealPeriod": meal_period
        }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with self.session.get(availability_url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('availableTimes', [])
                else:
                    logger.error(f"Availability check failed: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Availability check error: {e}")
            return []
    
    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()

class Database:
    """Handle database operations for storing dining requests"""
    
    def __init__(self, db_path: str = "dining_requests.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Update database schema to include location_id
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dining_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                location TEXT NOT NULL,
                location_id TEXT,
                restaurant_id TEXT NOT NULL,
                restaurant_name TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                requested_date TEXT NOT NULL,
                meal_period TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Add location_id column if it doesn't exist (for existing databases)
        try:
            cursor.execute('ALTER TABLE dining_requests ADD COLUMN location_id TEXT')
        except sqlite3.OperationalError:
            # Column already exists
            pass
        
        conn.commit()
        conn.close()
    
    def add_request(self, user_id: str, location: str, restaurant_id: str, 
                   restaurant_name: str, party_size: int, requested_date: str, 
                   meal_period: str, location_id: str = None):
        """Add a new dining request"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO dining_requests 
            (user_id, location, location_id, restaurant_id, restaurant_name, party_size, requested_date, meal_period)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, location, location_id, restaurant_id, restaurant_name, party_size, requested_date, meal_period))
        
        conn.commit()
        conn.close()
    
    def get_active_requests(self) -> List[Dict]:
        """Get all active dining requests"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM dining_requests WHERE active = 1
        ''')
        
        requests = []
        for row in cursor.fetchall():
            requests.append({
                'id': row[0],
                'user_id': row[1],
                'location': row[2],
                'location_id': row[3],
                'restaurant_id': row[4],
                'restaurant_name': row[5],
                'party_size': row[6],
                'requested_date': row[7],
                'meal_period': row[8],
                'created_at': row[9],
                'active': row[10]
            })
        
        conn.close()
        return requests
    
    def deactivate_request(self, request_id: int):
        """Deactivate a dining request"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE dining_requests SET active = 0 WHERE id = ?
        ''', (request_id,))
        
        conn.commit()
        conn.close()

class DiningRequestView(discord.ui.View):
    """Interactive view for dining request setup"""
    
    def __init__(self, bot, disney_api: DisneyAPI, db: Database):
        super().__init__(timeout=300)
        self.bot = bot
        self.disney_api = disney_api
        self.db = db
        self.user_data = {}
        self.locations = []
    
    async def load_locations(self):
        """Load locations from Disney API"""
        self.locations = await self.disney_api.get_locations()
        return self.locations
    
    def create_location_select(self):
        """Create location select menu from API data"""
        if not self.locations:
            return None
        
        # Create options from actual Disney API data
        options = []
        for location in self.locations[:25]:  # Discord limit of 25 options
            options.append(discord.SelectOption(
                label=location['name'],
                value=location['id'],
                description=f"Type: {location.get('type', 'Unknown')}"
            ))
        
        location_select = discord.ui.Select(
            placeholder="Select a Disney location...",
            options=options
        )
        
        return location_select
    
    async def handle_location_select(self, interaction: discord.Interaction, location_id: str):
        """Handle location selection and load restaurants"""
        # Find the selected location
        selected_location = next((loc for loc in self.locations if loc['id'] == location_id), None)
        if not selected_location:
            await interaction.response.send_message("Invalid location selected.", ephemeral=True)
            return
        
        # Store user selection
        self.user_data[interaction.user.id] = {
            "location_id": location_id,
            "location_name": selected_location['name']
        }
        
        # Get restaurants for this location from Disney API
        restaurants = await self.disney_api.get_restaurants(location_id)
        
        if not restaurants:
            await interaction.response.send_message(
                f"No restaurants found for {selected_location['name']} or API error occurred.",
                ephemeral=True
            )
            return
        
        # Create restaurant select menu from API data
        restaurant_options = []
        for restaurant in restaurants[:25]:  # Discord limit
            description = f"Cuisine: {restaurant.get('cuisine_type', 'Various')}"
            if restaurant.get('meal_periods'):
                description += f" | Meals: {', '.join(restaurant['meal_periods'])}"
            
            restaurant_options.append(discord.SelectOption(
                label=restaurant["name"],
                value=restaurant["id"],
                description=description[:100]  # Discord description limit
            ))
        
        restaurant_select = discord.ui.Select(
            placeholder="Select a restaurant...",
            options=restaurant_options
        )
        
        async def restaurant_callback(restaurant_interaction):
            restaurant_id = restaurant_select.values[0]
            restaurant_name = next(r["name"] for r in restaurants if r["id"] == restaurant_id)
            selected_restaurant = next(r for r in restaurants if r["id"] == restaurant_id)
            
            self.user_data[interaction.user.id]["restaurant_id"] = restaurant_id
            self.user_data[interaction.user.id]["restaurant_name"] = restaurant_name
            self.user_data[interaction.user.id]["available_meal_periods"] = selected_restaurant.get('meal_periods', [])
            
            # Create party size modal
            party_modal = PartyModal(self.user_data, self.db)
            await restaurant_interaction.response.send_modal(party_modal)
        
        restaurant_select.callback = restaurant_callback
        
        view = discord.ui.View()
        view.add_item(restaurant_select)
        
        await interaction.response.edit_message(
            content=f"You selected **{selected_location['name']}**. Now choose a restaurant:",
            view=view
        )

class PartyModal(discord.ui.Modal):
    """Modal for party size, date, and meal period input"""
    
    def __init__(self, user_data: Dict, db: Database):
        super().__init__(title="Dining Request Details")
        self.user_data = user_data
        self.db = db
        
        self.party_size = discord.ui.TextInput(
            label="Party Size",
            placeholder="Enter number of people (1-20)",
            min_length=1,
            max_length=2
        )
        
        self.date = discord.ui.TextInput(
            label="Requested Date",
            placeholder="YYYY-MM-DD (e.g., 2024-12-25)",
            min_length=10,
            max_length=10
        )
        
        self.meal_period = discord.ui.TextInput(
            label="Meal Period",
            placeholder="Available: " + ", ".join(self.user_data.get(list(self.user_data.keys())[0], {}).get('available_meal_periods', ['Breakfast', 'Lunch', 'Dinner'])),
            min_length=5,
            max_length=9
        )
        
        self.add_item(self.party_size)
        self.add_item(self.date)
        self.add_item(self.meal_period)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        try:
            party_size = int(self.party_size.value)
            date = self.date.value
            meal_period = self.meal_period.value.lower().capitalize()
            
            # Validate inputs
            if party_size < 1 or party_size > 20:
                await interaction.response.send_message("Party size must be between 1 and 20.", ephemeral=True)
                return
            
            # Validate meal period against available periods for this restaurant
            user_data = self.user_data.get(interaction.user.id, {})
            available_periods = user_data.get('available_meal_periods', ['Breakfast', 'Lunch', 'Dinner'])
            
            if meal_period not in available_periods:
                available_str = ", ".join(available_periods)
                await interaction.response.send_message(
                    f"Meal period must be one of: {available_str}.", 
                    ephemeral=True
                )
                return
            
            # Validate date format
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                await interaction.response.send_message("Date must be in YYYY-MM-DD format.", ephemeral=True)
                return
            
            # Store the request
            user_id = str(interaction.user.id)
            data = self.user_data[interaction.user.id]
            
            self.db.add_request(
                user_id=user_id,
                location=data["location_name"],
                location_id=data["location_id"],
                restaurant_id=data["restaurant_id"],
                restaurant_name=data["restaurant_name"],
                party_size=party_size,
                requested_date=date,
                meal_period=meal_period
            )
            
            await interaction.response.send_message(
                f"✅ **Dining alert set up successfully!**\n\n"
                f"**Restaurant:** {data['restaurant_name']}\n"
                f"**Location:** {data['location_name']}\n"
                f"**Party Size:** {party_size}\n"
                f"**Date:** {date}\n"
                f"**Meal Period:** {meal_period}\n\n"
                f"I'll check for availability every 5 minutes and DM you when I find a match!",
                ephemeral=True
            )
            
        except ValueError:
            await interaction.response.send_message("Invalid party size. Please enter a number.", ephemeral=True)

class DisneyDiningBot(commands.Bot):
    """Main Discord bot class"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        self.disney_api = DisneyAPI(
            username=os.getenv('DISNEY_USERNAME'),
            password=os.getenv('DISNEY_PASSWORD')
        )
        self.db = Database()
        
    async def setup_hook(self):
        """Set up the bot"""
        await self.disney_api.login()
        self.availability_checker.start()
        logger.info("Bot setup complete")
    
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f'{self.user} has connected to Discord!')
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    @tasks.loop(minutes=5)
    async def availability_checker(self):
        """Check for dining availability every 5 minutes"""
        requests = self.db.get_active_requests()
        
        for request in requests:
            try:
                availability = await self.disney_api.check_availability(
                    restaurant_id=request['restaurant_id'],
                    party_size=request['party_size'],
                    date=request['requested_date'],
                    meal_period=request['meal_period']
                )
                
                if availability:
                    # Send DM to user
                    user = self.get_user(int(request['user_id']))
                    if user:
                        embed = discord.Embed(
                            title="🎉 Dining Availability Found!",
                            description=f"A reservation is available for **{request['restaurant_name']}**!",
                            color=0x00ff00
                        )
                        
                        embed.add_field(name="Restaurant", value=request['restaurant_name'], inline=True)
                        embed.add_field(name="Location", value=request['location'], inline=True)
                        embed.add_field(name="Party Size", value=request['party_size'], inline=True)
                        embed.add_field(name="Date", value=request['requested_date'], inline=True)
                        embed.add_field(name="Meal Period", value=request['meal_period'], inline=True)
                        
                        available_times = ", ".join([time['time'] for time in availability[:5]])
                        embed.add_field(name="Available Times", value=available_times, inline=False)
                        
                        # Disney booking link (this would need to be the actual booking URL)
                        booking_url = f"https://disneyworld.disney.go.com/dining/reservations/?restaurant={request['restaurant_id']}&date={request['requested_date']}"
                        embed.add_field(name="Book Now", value=f"[Click here to book]({booking_url})", inline=False)
                        
                        try:
                            await user.send(embed=embed)
                            # Deactivate the request
                            self.db.deactivate_request(request['id'])
                            logger.info(f"Sent availability alert to user {request['user_id']}")
                        except discord.Forbidden:
                            logger.warning(f"Could not send DM to user {request['user_id']}")
                
            except Exception as e:
                logger.error(f"Error checking availability for request {request['id']}: {e}")
    
    @availability_checker.before_loop
    async def before_availability_checker(self):
        """Wait for bot to be ready before starting the checker"""
        await self.wait_until_ready()

# Create bot instance
bot = DisneyDiningBot()

@bot.tree.command(name="request", description="Set up a dining alert for Disney World restaurants")
async def dining_request(interaction: discord.Interaction):
    """Slash command to start dining request setup"""
    # Create view and load locations from Disney API
    view = DiningRequestView(bot, bot.disney_api, bot.db)
    
    # Load locations from Disney API
    locations = await view.load_locations()
    
    if not locations:
        await interaction.response.send_message(
            "❌ Unable to load Disney locations. Please try again later.",
            ephemeral=True
        )
        return
    
    # Create location select menu
    location_select = view.create_location_select()
    
    if not location_select:
        await interaction.response.send_message(
            "❌ No locations available. Please try again later.",
            ephemeral=True
        )
        return
    
    # Add callback to location select
    async def location_callback(location_interaction):
        location_id = location_select.values[0]
        await view.handle_location_select(location_interaction, location_id)
    
    location_select.callback = location_callback
    
    # Create new view with the location select
    new_view = discord.ui.View()
    new_view.add_item(location_select)
    
    embed = discord.Embed(
        title="🏰 Disney Dining Alert Setup",
        description=f"Let's set up your dining alert! First, select a Disney location:\n\n*Found {len(locations)} locations*",
        color=0x0099ff
    )
    
    await interaction.response.send_message(embed=embed, view=new_view, ephemeral=True)

@bot.tree.command(name="myrequests", description="View your active dining requests")
async def my_requests(interaction: discord.Interaction):
    """Show user's active dining requests"""
    user_id = str(interaction.user.id)
    
    conn = sqlite3.connect(bot.db.db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM dining_requests WHERE user_id = ? AND active = 1
    ''', (user_id,))
    
    requests = cursor.fetchall()
    conn.close()
    
    if not requests:
        await interaction.response.send_message("You don't have any active dining requests.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="Your Active Dining Requests",
        color=0x0099ff
    )
    
    for request in requests:
        embed.add_field(
            name=f"{request[5]} ({request[2]})",
            value=f"Party Size: {request[6]}\nDate: {request[7]}\nMeal: {request[8]}",
            inline=True
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Run the bot
if __name__ == "__main__":
    # Make sure to set these environment variables
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set")
        exit(1)
    
    if not os.getenv('DISNEY_USERNAME') or not os.getenv('DISNEY_PASSWORD'):
        logger.error("Disney credentials not set in environment variables")
        exit(1)
    
    bot.run(DISCORD_TOKEN)
