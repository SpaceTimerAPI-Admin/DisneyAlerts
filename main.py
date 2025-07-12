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
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DisneyWebScraper:
    """Handles Disney website scraping to mimic real browser behavior"""
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session = None
        self.ua = UserAgent()
        self.logged_in = False
        
        # Real Disney URLs (these are actual endpoints)
        self.base_url = "https://disneyworld.disney.go.com"
        self.login_url = "https://disneyworld.disney.go.com/authentication/get-login-form/"
        self.dining_url = "https://disneyworld.disney.go.com/dining/"
        self.availability_url = "https://disneyworld.disney.go.com/finder/api/v1/explorer-service/public/finder/dining-availability"
        
    async def create_session(self):
        """Create aiohttp session with browser-like headers"""
        headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=timeout,
            cookie_jar=aiohttp.CookieJar()
        )
    
    async def login(self):
        """Login to Disney website by scraping the login form"""
        try:
            if not self.session:
                await self.create_session()
            
            logger.info(f"Attempting Disney website login for: {self.username}")
            
            # Step 1: Get the login page to extract form data and cookies
            async with self.session.get(self.login_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get login page: {response.status}")
                    return False
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract CSRF token or other hidden form fields
                csrf_token = None
                csrf_input = soup.find('input', {'name': '_token'}) or soup.find('input', {'name': 'authenticity_token'})
                if csrf_input:
                    csrf_token = csrf_input.get('value')
                
                logger.info(f"Extracted CSRF token: {bool(csrf_token)}")
            
            # Step 2: Submit login form
            login_data = {
                'loginValue': self.username,
                'password': self.password
            }
            
            if csrf_token:
                login_data['_token'] = csrf_token
            
            # Update headers for form submission
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': self.login_url,
                'Origin': 'https://disneyworld.disney.go.com'
            })
            
            async with self.session.post(self.login_url, data=login_data) as response:
                logger.info(f"Login response status: {response.status}")
                
                # Check if login was successful
                if response.status == 200:
                    response_text = await response.text()
                    
                    # Look for success indicators in the response
                    if 'dashboard' in response_text.lower() or 'profile' in response_text.lower():
                        logger.info("Disney login successful")
                        self.logged_in = True
                        return True
                    else:
                        logger.warning("Login may have failed - no success indicators found")
                        return False
                elif response.status == 302:
                    # Redirect usually means success
                    logger.info("Disney login successful (redirected)")
                    self.logged_in = True
                    return True
                else:
                    logger.error(f"Login failed with status: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Disney login error: {e}")
            return False
    
    async def get_locations(self) -> List[Dict]:
        """Scrape Disney dining locations from the website"""
        try:
            if not self.session:
                await self.create_session()
            
            locations = []
            
            # Scrape dining page for locations
            async with self.session.get(f"{self.dining_url}") as response:
                if response.status != 200:
                    logger.error(f"Failed to get dining page: {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for location filters or dropdowns
                location_elements = soup.find_all(['option', 'div'], class_=re.compile(r'location|resort|park', re.I))
                
                for element in location_elements:
                    location_name = element.get_text(strip=True)
                    location_id = element.get('value') or element.get('data-id')
                    
                    if location_name and location_id and len(location_name) > 2:
                        locations.append({
                            'id': location_id,
                            'name': location_name,
                            'type': 'park' if any(park in location_name.lower() for park in ['kingdom', 'epcot', 'studios', 'animal']) else 'resort'
                        })
                
                # If we don't find dynamic locations, use known Disney locations
                if not locations:
                    logger.info("Using fallback location list")
                    locations = [
                        {'id': 'magic-kingdom', 'name': 'Magic Kingdom', 'type': 'park'},
                        {'id': 'epcot', 'name': 'EPCOT', 'type': 'park'},
                        {'id': 'hollywood-studios', 'name': "Disney's Hollywood Studios", 'type': 'park'},
                        {'id': 'animal-kingdom', 'name': "Disney's Animal Kingdom", 'type': 'park'},
                        {'id': 'disney-springs', 'name': 'Disney Springs', 'type': 'shopping'},
                        {'id': 'grand-floridian', 'name': "Disney's Grand Floridian Resort", 'type': 'resort'},
                        {'id': 'polynesian', 'name': "Disney's Polynesian Village Resort", 'type': 'resort'},
                        {'id': 'contemporary', 'name': "Disney's Contemporary Resort", 'type': 'resort'}
                    ]
                
                logger.info(f"Found {len(locations)} Disney locations")
                return locations
                
        except Exception as e:
            logger.error(f"Error getting locations: {e}")
            return []
    
    async def get_restaurants(self, location_id: str) -> List[Dict]:
        """Scrape restaurants for a specific location"""
        try:
            if not self.session:
                await self.create_session()
            
            restaurants = []
            search_url = f"{self.dining_url}?location={location_id}"
            
            async with self.session.get(search_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get restaurants for {location_id}: {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for restaurant cards or listings
                restaurant_elements = soup.find_all(['div', 'article'], class_=re.compile(r'restaurant|dining|card', re.I))
                
                for element in restaurant_elements:
                    name_elem = element.find(['h2', 'h3', 'h4', 'a'], class_=re.compile(r'title|name|heading', re.I))
                    if not name_elem:
                        continue
                    
                    restaurant_name = name_elem.get_text(strip=True)
                    restaurant_link = name_elem.get('href') if name_elem.name == 'a' else element.find('a', href=True)
                    restaurant_id = None
                    
                    if restaurant_link:
                        # Extract ID from URL
                        if isinstance(restaurant_link, str):
                            url = restaurant_link
                        else:
                            url = restaurant_link.get('href', '')
                        
                        # Extract restaurant ID from URL - simplified approach
                        url_parts = url.strip('/').split('/')
                        if url_parts:
                            restaurant_id = url_parts[-1]
                    
                    if restaurant_name and restaurant_id:
                        # Look for cuisine type
                        cuisine_elem = element.find(text=re.compile(r'cuisine|american|italian|mexican|asian', re.I))
                        cuisine_type = cuisine_elem.strip() if cuisine_elem else 'Various'
                        
                        restaurants.append({
                            'id': restaurant_id,
                            'name': restaurant_name,
                            'location_id': location_id,
                            'cuisine_type': cuisine_type,
                            'meal_periods': ['Breakfast', 'Lunch', 'Dinner'],  # Default - would need more scraping
                            'accepts_reservations': True  # Assume all listed restaurants accept reservations
                        })
                
                logger.info(f"Found {len(restaurants)} restaurants for {location_id}")
                return restaurants[:25]  # Limit to Discord's dropdown limit
                
        except Exception as e:
            logger.error(f"Error getting restaurants for {location_id}: {e}")
            return []
    
    async def check_availability(self, restaurant_id: str, party_size: int, date: str, meal_period: str) -> List[Dict]:
        """Check real availability by scraping Disney's availability checker"""
        try:
            if not self.session:
                await self.create_session()
            
            # Format date for Disney's API
            search_date = datetime.strptime(date, "%Y-%m-%d").strftime("%m/%d/%Y")
            
            # Disney's availability API parameters
            params = {
                'searchDate': search_date,
                'partySize': party_size,
                'preferredTime': self.get_meal_time(meal_period),
                'restaurantId': restaurant_id
            }
            
            async with self.session.get(self.availability_url, params=params) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        
                        # Parse availability from Disney's response
                        available_times = []
                        if 'offers' in data:
                            for offer in data['offers']:
                                if offer.get('available', False):
                                    available_times.append({
                                        'time': offer.get('time', ''),
                                        'id': offer.get('id', ''),
                                        'url': f"{self.base_url}/dining/reservation/{offer.get('id', '')}"
                                    })
                        
                        return available_times
                        
                    except json.JSONDecodeError:
                        # If not JSON, try scraping HTML response
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Look for time slots in HTML
                        time_elements = soup.find_all(['button', 'a'], text=re.compile(r'\d+:\d+'))
                        available_times = []
                        
                        for elem in time_elements:
                            time_text = elem.get_text(strip=True)
                            available_times.append({
                                'time': time_text,
                                'id': elem.get('data-id', ''),
                                'url': elem.get('href', '')
                            })
                        
                        return available_times
                else:
                    logger.error(f"Availability check failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return []
    
    def get_meal_time(self, meal_period: str) -> str:
        """Convert meal period to Disney's expected time format"""
        meal_times = {
            'breakfast': '08:00',
            'lunch': '12:00', 
            'dinner': '18:00'
        }
        return meal_times.get(meal_period.lower(), '12:00')
    
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
    
    def __init__(self, bot, disney_api: DisneyWebScraper, db: Database):
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
        
        self.disney_api = DisneyWebScraper(
            username=os.getenv('DISNEY_USERNAME'),
            password=os.getenv('DISNEY_PASSWORD')
        )
        self.db = Database()
        
    async def setup_hook(self):
        """Set up the bot"""
        logger.info("Bot setup hook started")
        try:
            # Try Disney login but don't let it block the bot startup
            logger.info("Attempting Disney API login...")
            login_success = await asyncio.wait_for(self.disney_api.login(), timeout=30.0)
            if login_success:
                logger.info("Disney API login successful")
            else:
                logger.warning("Disney API login failed - will retry during availability checks")
        except asyncio.TimeoutError:
            logger.warning("Disney API login timed out - will retry later")
        except Exception as e:
            logger.error(f"Disney API login error: {e} - will retry later")
        
        # Start availability checker regardless of Disney login status
        self.availability_checker.start()
        logger.info("Availability checker started")
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
    
    print(f"Discord token present: {bool(DISCORD_TOKEN)}")
    print(f"Disney username present: {bool(os.getenv('DISNEY_USERNAME'))}")
    print(f"Disney password present: {bool(os.getenv('DISNEY_PASSWORD'))}")
    
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set")
        exit(1)
    
    if not os.getenv('DISNEY_USERNAME') or not os.getenv('DISNEY_PASSWORD'):
        logger.error("Disney credentials not set in environment variables")
        exit(1)
    
    print("Starting bot...")
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        exit(1)
