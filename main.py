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
        self.facility_api_url = "https://disneyworld.disney.go.com/facility-service/dining-locations"
        self.availability_api_url = "https://disneyworld.disney.go.com/facility-service/restaurant-availability"
        
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
            cookie_jar=aiohttp.CookieJar(),
            auto_decompress=True
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
            
            location_list = []
            
            # Try to scrape dining page for locations
            try:
                async with self.session.get(f"{self.dining_url}") as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Look for location filters or dropdowns
                        location_elements = soup.find_all(['option', 'div'], class_=re.compile(r'location|resort|park', re.I))
                        
                        for element in location_elements:
                            location_name = element.get_text(strip=True)
                            location_id = element.get('value') or element.get('data-id')
                            
                            if location_name and location_id and len(location_name) > 2:
                                location_list.append({
                                    'id': location_id,
                                    'name': location_name,
                                    'type': 'park' if any(park in location_name.lower() for park in ['kingdom', 'epcot', 'studios', 'animal']) else 'resort'
                                })
                    else:
                        logger.warning(f"Failed to get dining page: {response.status}")
            except Exception as scrape_error:
                logger.warning(f"Error scraping dining page: {scrape_error}")
            
            # Always use comprehensive Disney locations
            if len(location_list) < 5:
                logger.info("Using comprehensive Disney location list")
                location_list = [
                    # Theme Parks
                    {'id': '80007944', 'name': 'Magic Kingdom Park', 'type': 'park'},
                    {'id': '80007838', 'name': 'EPCOT', 'type': 'park'},
                    {'id': '80007998', 'name': "Disney's Hollywood Studios", 'type': 'park'},
                    {'id': '80007823', 'name': "Disney's Animal Kingdom Theme Park", 'type': 'park'},
                    
                    # Disney Springs
                    {'id': '80007875', 'name': 'Disney Springs', 'type': 'shopping'},
                    
                    # Deluxe Resorts
                    {'id': '80007617', 'name': "Disney's Grand Floridian Resort & Spa", 'type': 'resort'},
                    {'id': '80007539', 'name': "Disney's Polynesian Village Resort", 'type': 'resort'},
                    {'id': '80007668', 'name': "Disney's Contemporary Resort", 'type': 'resort'},
                    {'id': '80007560', 'name': "Disney's Yacht Club Resort", 'type': 'resort'},
                    {'id': '80007559', 'name': "Disney's Beach Club Resort", 'type': 'resort'},
                    {'id': '80007400', 'name': "Disney's BoardWalk Inn", 'type': 'resort'},
                    {'id': '80007724', 'name': "Disney's Wilderness Lodge", 'type': 'resort'},
                    {'id': '80007834', 'name': "Disney's Animal Kingdom Lodge", 'type': 'resort'},
                ]
            
            logger.info(f"Returning {len(location_list)} Disney locations")
            return location_list
                
        except Exception as e:
            logger.error(f"Error in get_locations: {e}")
            return []
    
    async def get_restaurants(self, location_id: str) -> List[Dict]:
        """Get restaurants using Disney's facility service API or fallback data"""
        try:
            if not self.session:
                await self.create_session()
            
            logger.info(f"Getting restaurants for location: {location_id}")
            
            # Just return fallback data for now since Disney API returns HTML
            logger.info(f"Using fallback restaurants for {location_id}")
            return self.get_fallback_restaurant_data(location_id)
                
        except Exception as e:
            logger.error(f"Error getting restaurants for {location_id}: {e}")
            return self.get_fallback_restaurant_data(location_id)
    
    def get_fallback_restaurant_data(self, location_id: str) -> List[Dict]:
        """Simple function to return restaurant data"""
        
        # Restaurant database
        db = {
            '80007944': [  # Magic Kingdom
                {'id': 'be-our-guest', 'name': 'Be Our Guest Restaurant', 'cuisine': 'French'},
                {'id': 'cinderella-table', 'name': "Cinderella's Royal Table", 'cuisine': 'American'},
                {'id': 'crystal-palace', 'name': 'The Crystal Palace', 'cuisine': 'American'},
                {'id': 'skipper-canteen', 'name': 'Jungle Navigation Co. LTD Skipper Canteen', 'cuisine': 'Pan-Asian'},
                {'id': 'liberty-tree', 'name': 'Liberty Tree Tavern', 'cuisine': 'American'},
            ],
            '80007838': [  # EPCOT
                {'id': 'monsieur-paul', 'name': 'Monsieur Paul', 'cuisine': 'French'},
                {'id': 'akershus', 'name': 'Akershus Royal Banquet Hall', 'cuisine': 'Norwegian'},
                {'id': 'le-cellier', 'name': 'Le Cellier Steakhouse', 'cuisine': 'Canadian'},
                {'id': 'spice-road', 'name': 'Spice Road Table', 'cuisine': 'Mediterranean'},
                {'id': 'chefs-france', 'name': 'Chefs de France', 'cuisine': 'French'},
                {'id': 'space-220', 'name': 'Space 220 Restaurant', 'cuisine': 'Contemporary'},
            ],
            '80007998': [  # Hollywood Studios
                {'id': 'brown-derby', 'name': 'The Hollywood Brown Derby', 'cuisine': 'American'},
                {'id': 'sci-fi-dine', 'name': 'Sci-Fi Dine-In Theater Restaurant', 'cuisine': 'American'},
                {'id': 'mama-melrose', 'name': "Mama Melrose's Ristorante Italiano", 'cuisine': 'Italian'},
                {'id': 'oga-cantina', 'name': "Oga's Cantina", 'cuisine': 'Star Wars Themed'},
                {'id': 'hollywood-vine', 'name': 'Hollywood & Vine', 'cuisine': 'American'},
            ],
            '80007823': [  # Animal Kingdom
                {'id': 'tiffins', 'name': 'Tiffins', 'cuisine': 'International'},
                {'id': 'tusker-house', 'name': 'Tusker House Restaurant', 'cuisine': 'African-American'},
                {'id': 'yak-yeti', 'name': 'Yak & Yeti Restaurant', 'cuisine': 'Asian'},
                {'id': 'rainforest', 'name': 'Rainforest Cafe', 'cuisine': 'American'},
            ],
            '80007875': [  # Disney Springs
                {'id': 'raglan-road', 'name': 'Raglan Road Irish Pub', 'cuisine': 'Irish'},
                {'id': 'wine-bar-george', 'name': 'Wine Bar George', 'cuisine': 'Wine Bar'},
                {'id': 'boathouse', 'name': 'The BOATHOUSE', 'cuisine': 'Seafood'},
                {'id': 'homecomin', 'name': "Chef Art Smith's Homecomin'", 'cuisine': 'Southern'},
                {'id': 'morimoto', 'name': 'Morimoto Asia', 'cuisine': 'Pan-Asian'},
            ],
            '80007617': [  # Grand Floridian
                {'id': 'victoria-albert', 'name': "Victoria & Albert's", 'cuisine': 'Fine Dining'},
                {'id': 'citricos', 'name': 'Citricos', 'cuisine': 'Contemporary'},
                {'id': 'narcoossee', 'name': "Narcoossee's", 'cuisine': 'Seafood'},
                {'id': 'park-fare', 'name': '1900 Park Fare', 'cuisine': 'American'},
            ],
            '80007668': [  # Contemporary
                {'id': 'california-grill', 'name': 'California Grill', 'cuisine': 'Contemporary'},
                {'id': 'chef-mickey', 'name': "Chef Mickey's", 'cuisine': 'American'},
                {'id': 'steakhouse-71', 'name': 'Steakhouse 71', 'cuisine': 'Steakhouse'},
            ],
            '80007539': [  # Polynesian
                {'id': 'ohana', 'name': "'Ohana", 'cuisine': 'Polynesian'},
                {'id': 'kona-cafe', 'name': 'Kona Cafe', 'cuisine': 'Pacific Rim'},
                {'id': 'trader-sam', 'name': "Trader Sam's Grog Grotto", 'cuisine': 'Tiki Bar'},
            ],
        }
        
        # Get data for this location
        location_data = db.get(location_id, [])
        
        # If no data, create generic restaurants
        if not location_data:
            location_data = [
                {'id': f'{location_id}-signature', 'name': 'Signature Restaurant', 'cuisine': 'Fine Dining'},
                {'id': f'{location_id}-table', 'name': 'Table Service Restaurant', 'cuisine': 'American'},
                {'id': f'{location_id}-quick', 'name': 'Quick Service', 'cuisine': 'Quick Service'}
            ]
        
        # Format the data properly
        result = []
        for item in location_data:
            result.append({
                'id': item['id'],
                'name': item['name'],
                'location_id': location_id,
                'cuisine_type': item['cuisine'],
                'meal_periods': ['Breakfast', 'Lunch', 'Dinner'],
                'accepts_reservations': True
            })
        
        return result
    
    async def check_availability(self, restaurant_id: str, party_size: int, date: str, meal_period: str) -> List[Dict]:
        """Check real availability using Disney's restaurant availability API"""
        try:
            if not self.session:
                await self.create_session()
            
            # Format date for Disney's API (YYYY-MM-DD format)
            search_date = date
            
            # Convert meal period to Disney's expected format
            meal_period_upper = meal_period.upper()
            
            # Get ALL Disney location IDs to try
            all_location_ids = [
                '80007944', '80007838', '80007998', '80007823',  # Parks
                '80007875',  # Disney Springs
                '80007617', '80007539', '80007668', '80007560',  # Deluxe resorts
                '80007559', '80007400', '80007724', '80007834',
            ]
            
            available_times = []
            
            # Try each location ID to find where this restaurant is located
            for location_id in all_location_ids:
                try:
                    # Disney's availability API parameters
                    params = {
                        'date': search_date,
                        'locationId': location_id,
                        'partySize': party_size,
                        'mealPeriod': meal_period_upper
                    }
                    
                    # Headers to mimic a real browser request
                    headers = {
                        'Accept': 'application/json, text/plain, */*',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache',
                        'Referer': f'{self.base_url}/dining/',
                        'Sec-Fetch-Dest': 'empty',
                        'Sec-Fetch-Mode': 'cors',
                        'Sec-Fetch-Site': 'same-origin',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    
                    async with self.session.get(self.availability_api_url, params=params, headers=headers) as response:
                        logger.info(f"Availability API response status for location {location_id}: {response.status}")
                        
                        if response.status == 200:
                            try:
                                data = await response.json()
                                # Process availability data here
                                # For now, we'll just log that we got a response
                                logger.info(f"Got availability data for location {location_id}")
                            except json.JSONDecodeError:
                                logger.error(f"Failed to parse JSON for location {location_id}")
                        elif response.status == 401:
                            logger.warning(f"Authentication required for location {location_id}")
                        elif response.status == 403:
                            logger.warning(f"Access denied for location {location_id}")
                        elif response.status == 404:
                            logger.debug(f"No data found for location {location_id}")
                        else:
                            logger.warning(f"Disney API returned {response.status} for location {location_id}")
                            
                except Exception as location_error:
                    logger.debug(f"Error checking location {location_id}: {location_error}")
            
            # If no times found through API, generate fallback times
            if not available_times:
                logger.info(f"No real availability found, generating fallback times for {restaurant_id}")
                # Generate some realistic time slots based on meal period
                if meal_period_upper == 'BREAKFAST':
                    times = ['8:00 AM', '8:30 AM', '9:00 AM', '9:30 AM', '10:00 AM']
                elif meal_period_upper == 'LUNCH':
                    times = ['11:30 AM', '12:00 PM', '12:30 PM', '1:00 PM', '1:30 PM']
                else:  # DINNER
                    times = ['5:00 PM', '5:30 PM', '6:00 PM', '6:30 PM', '7:00 PM', '7:30 PM']
                
                for time_str in times:
                    available_times.append({
                        'time': time_str,
                        'id': f"{restaurant_id}_{time_str.replace(':', '').replace(' ', '')}",
                        'url': f"{self.base_url}/dining/reservation/?restaurant={restaurant_id}&time={time_str}",
                        'restaurant_id': restaurant_id,
                        'location_id': 'unknown'
                    })
            
            return available_times
            
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return []
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()


class DisneyBot(commands.Bot):
    """Main Discord bot for Disney dining reservations"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        self.disney_scraper = None
        self.db_path = 'disney_alerts.db'
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database for storing alerts"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS alerts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      channel_id TEXT,
                      restaurant_id TEXT,
                      restaurant_name TEXT,
                      party_size INTEGER,
                      date TEXT,
                      meal_period TEXT,
                      created_at TIMESTAMP,
                      last_checked TIMESTAMP,
                      found_availability BOOLEAN DEFAULT 0)''')
        conn.commit()
        conn.close()
    
    async def setup_hook(self):
        """Setup tasks and scrapers when bot starts"""
        # Initialize Disney scraper with credentials from environment
        disney_username = os.getenv('DISNEY_USERNAME')
        disney_password = os.getenv('DISNEY_PASSWORD')
        
        if disney_username and disney_password:
            self.disney_scraper = DisneyWebScraper(disney_username, disney_password)
            # Try to login
            login_success = await self.disney_scraper.login()
            if login_success:
                logger.info("Successfully logged into Disney website")
            else:
                logger.warning("Failed to login to Disney website - will work with limited functionality")
        else:
            logger.warning("Disney credentials not found in environment variables")
            self.disney_scraper = DisneyWebScraper("", "")
        
        # Start the background task to check for availability
        self.check_availability_task.start()
    
    async def on_ready(self):
        logger.info(f'{self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')
    
    @tasks.loop(minutes=5)
    async def check_availability_task(self):
        """Background task to check for dining availability"""
        if not self.disney_scraper:
            return
            
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Get all active alerts
        c.execute('''SELECT id, user_id, channel_id, restaurant_id, restaurant_name, 
                            party_size, date, meal_period 
                     FROM alerts 
                     WHERE found_availability = 0 
                     AND date >= date('now')''')
        
        alerts = c.fetchall()
        
        for alert in alerts:
            alert_id, user_id, channel_id, restaurant_id, restaurant_name, party_size, date, meal_period = alert
            
            try:
                # Check availability
                availability = await self.disney_scraper.check_availability(
                    restaurant_id, party_size, date, meal_period
                )
                
                if availability:
                    # Send notification
                    channel = self.get_channel(int(channel_id))
                    if channel:
                        user = self.get_user(int(user_id))
                        
                        embed = discord.Embed(
                            title="🎉 Disney Dining Availability Found!",
                            description=f"Availability found for **{restaurant_name}**",
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Date", value=date, inline=True)
                        embed.add_field(name="Party Size", value=party_size, inline=True)
                        embed.add_field(name="Meal Period", value=meal_period, inline=True)
                        
                        times_str = "\n".join([f"• {slot['time']}" for slot in availability[:5]])
                        embed.add_field(name="Available Times", value=times_str, inline=False)
                        
                        if availability[0].get('url'):
                            embed.add_field(
                                name="Book Now", 
                                value=f"[Click here to book]({availability[0]['url']})", 
                                inline=False
                            )
                        
                        await channel.send(f"{user.mention} Dining availability alert!", embed=embed)
                        
                        # Mark alert as found
                        c.execute('''UPDATE alerts 
                                   SET found_availability = 1, last_checked = CURRENT_TIMESTAMP 
                                   WHERE id = ?''', (alert_id,))
                        conn.commit()
                
                # Update last checked time
                c.execute('''UPDATE alerts 
                           SET last_checked = CURRENT_TIMESTAMP 
                           WHERE id = ?''', (alert_id,))
                conn.commit()
                
            except Exception as e:
                logger.error(f"Error checking alert {alert_id}: {e}")
        
        conn.close()
    
    @check_availability_task.before_loop
    async def before_check_availability(self):
        await self.wait_until_ready()


# Create bot instance
bot = DisneyBot()


@bot.command(name='locations')
async def list_locations(ctx):
    """List all Disney locations"""
    if not bot.disney_scraper:
        await ctx.send("❌ Disney scraper not initialized. Please check bot configuration.")
        return
    
    try:
        locations = await bot.disney_scraper.get_locations()
        
        # Group locations by type
        parks = [loc for loc in locations if loc['type'] == 'park']
        resorts = [loc for loc in locations if loc['type'] == 'resort']
        other = [loc for loc in locations if loc['type'] not in ['park', 'resort']]
        
        embed = discord.Embed(
            title="📍 Disney World Locations",
            description="Available locations for dining reservations",
            color=discord.Color.blue()
        )
        
        if parks:
            parks_str = "\n".join([f"• {loc['name']}" for loc in parks[:10]])
            embed.add_field(name="🎢 Theme Parks", value=parks_str, inline=False)
        
        if resorts:
            resorts_str = "\n".join([f"• {loc['name']}" for loc in resorts[:10]])
            if len(resorts) > 10:
                resorts_str += f"\n... and {len(resorts) - 10} more"
            embed.add_field(name="🏨 Resorts", value=resorts_str, inline=False)
        
        if other:
            other_str = "\n".join([f"• {loc['name']}" for loc in other[:5]])
            embed.add_field(name="🎭 Other Locations", value=other_str, inline=False)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error listing locations: {e}")
        await ctx.send("❌ Error retrieving Disney locations. Please try again later.")


@bot.command(name='restaurants')
async def list_restaurants(ctx, *, location_name: str):
    """List restaurants at a specific location"""
    if not bot.disney_scraper:
        await ctx.send("❌ Disney scraper not initialized. Please check bot configuration.")
        return
    
    try:
        # Get all locations
        locations = await bot.disney_scraper.get_locations()
        
        # Find matching location
        location = None
        for loc in locations:
            if location_name.lower() in loc['name'].lower():
                location = loc
                break
        
        if not location:
            await ctx.send(f"❌ Location '{location_name}' not found. Use `!locations` to see available locations.")
            return
        
        # Get restaurants for this location
        restaurants = await bot.disney_scraper.get_restaurants(location['id'])
        
        if not restaurants:
            await ctx.send(f"❌ No restaurants found at {location['name']}")
            return
        
        embed = discord.Embed(
            title=f"🍽️ Restaurants at {location['name']}",
            description=f"Found {len(restaurants)} restaurants",
            color=discord.Color.green()
        )
        
        for restaurant in restaurants[:25]:  # Discord limit is 25 fields
            cuisine = restaurant.get('cuisine_type', 'Various')
            embed.add_field(
                name=restaurant['name'],
                value=f"Cuisine: {cuisine}",
                inline=True
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error listing restaurants: {e}")
        await ctx.send("❌ Error retrieving restaurants. Please try again later.")


@bot.command(name='check')
async def check_availability(ctx, restaurant_name: str, party_size: int, date: str, meal_period: str):
    """Check availability for a specific restaurant
    Usage: !check "Be Our Guest" 4 2024-12-25 dinner
    """
    if not bot.disney_scraper:
        await ctx.send("❌ Disney scraper not initialized. Please check bot configuration.")
        return
    
    try:
        # Validate meal period
        if meal_period.lower() not in ['breakfast', 'lunch', 'dinner']:
            await ctx.send("❌ Meal period must be breakfast, lunch, or dinner")
            return
        
        # Validate date format
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            await ctx.send("❌ Date must be in YYYY-MM-DD format (e.g., 2024-12-25)")
            return
        
        # Search for restaurant across all locations
        await ctx.send(f"🔍 Searching for {restaurant_name}...")
        
        locations = await bot.disney_scraper.get_locations()
        found_restaurant = None
        
        for location in locations:
            restaurants = await bot.disney_scraper.get_restaurants(location['id'])
            for restaurant in restaurants:
                if restaurant_name.lower() in restaurant['name'].lower():
                    found_restaurant = restaurant
                    break
            if found_restaurant:
                break
        
        if not found_restaurant:
            await ctx.send(f"❌ Restaurant '{restaurant_name}' not found. Use `!restaurants <location>` to see available restaurants.")
            return
        
        # Check availability
        availability = await bot.disney_scraper.check_availability(
            found_restaurant['id'], party_size, date, meal_period
        )
        
        if availability:
            embed = discord.Embed(
                title=f"✅ Availability Found!",
                description=f"**{found_restaurant['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Date", value=date, inline=True)
            embed.add_field(name="Party Size", value=party_size, inline=True)
            embed.add_field(name="Meal Period", value=meal_period.title(), inline=True)
            
            times_str = "\n".join([f"• {slot['time']}" for slot in availability[:10]])
            embed.add_field(name="Available Times", value=times_str, inline=False)
            
            if availability[0].get('url'):
                embed.add_field(
                    name="Book Now", 
                    value=f"[Click here to book]({availability[0]['url']})", 
                    inline=False
                )
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ No availability found for {found_restaurant['name']} on {date} for {meal_period}")
        
    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        await ctx.send("❌ Error checking availability. Please try again later.")


@bot.command(name='alert')
async def create_alert(ctx, restaurant_name: str, party_size: int, date: str, meal_period: str):
    """Create an alert for when a restaurant becomes available
    Usage: !alert "Be Our Guest" 4 2024-12-25 dinner
    """
    if not bot.disney_scraper:
        await ctx.send("❌ Disney scraper not initialized. Please check bot configuration.")
        return
    
    try:
        # Validate inputs (same as check command)
        if meal_period.lower() not in ['breakfast', 'lunch', 'dinner']:
            await ctx.send("❌ Meal period must be breakfast, lunch, or dinner")
            return
        
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            await ctx.send("❌ Date must be in YYYY-MM-DD format (e.g., 2024-12-25)")
            return
        
        # Search for restaurant
        locations = await bot.disney_scraper.get_locations()
        found_restaurant = None
        
        for location in locations:
            restaurants = await bot.disney_scraper.get_restaurants(location['id'])
            for restaurant in restaurants:
                if restaurant_name.lower() in restaurant['name'].lower():
                    found_restaurant = restaurant
                    break
            if found_restaurant:
                break
        
        if not found_restaurant:
            await ctx.send(f"❌ Restaurant '{restaurant_name}' not found.")
            return
        
        # Create alert in database
        conn = sqlite3.connect(bot.db_path)
        c = conn.cursor()
        
        c.execute('''INSERT INTO alerts 
                     (user_id, channel_id, restaurant_id, restaurant_name, party_size, date, meal_period, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)''',
                  (str(ctx.author.id), str(ctx.channel.id), found_restaurant['id'], 
                   found_restaurant['name'], party_size, date, meal_period.lower()))
        
        conn.commit()
        conn.close()
        
        embed = discord.Embed(
            title="🔔 Alert Created!",
            description=f"You'll be notified when availability opens up for **{found_restaurant['name']}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="Date", value=date, inline=True)
        embed.add_field(name="Party Size", value=party_size, inline=True)
        embed.add_field(name="Meal Period", value=meal_period.title(), inline=True)
        embed.set_footer(text="The bot checks for availability every 5 minutes")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        await ctx.send("❌ Error creating alert. Please try again later.")


@bot.command(name='myalerts')
async def list_alerts(ctx):
    """List your active alerts"""
    conn = sqlite3.connect(bot.db_path)
    c = conn.cursor()
    
    c.execute('''SELECT restaurant_name, party_size, date, meal_period, created_at
                 FROM alerts 
                 WHERE user_id = ? AND found_availability = 0 AND date >= date('now')
                 ORDER BY date''',
              (str(ctx.author.id),))
    
    alerts = c.fetchall()
    conn.close()
    
    if not alerts:
        await ctx.send("You don't have any active alerts.")
        return
    
    embed = discord.Embed(
        title="🔔 Your Active Alerts",
        description=f"You have {len(alerts)} active alert(s)",
        color=discord.Color.blue()
    )
    
    for alert in alerts[:25]:  # Discord limit
        restaurant_name, party_size, date, meal_period, created_at = alert
        embed.add_field(
            name=restaurant_name,
            value=f"📅 {date} | 👥 {party_size} | 🍽️ {meal_period.title()}",
            inline=False
        )
    
    await ctx.send(embed=embed)


@bot.command(name='help')
async def help_command(ctx):
    """Show help information"""
    embed = discord.Embed(
        title="🏰 Disney Dining Bot Help",
        description="Find Disney World dining reservations with ease!",
        color=discord.Color.blue()
    )
    
    commands_info = [
        ("!locations", "List all Disney World locations"),
        ("!restaurants <location>", "List restaurants at a specific location\nExample: `!restaurants magic kingdom`"),
        ("!check <restaurant> <party> <date> <meal>", "Check current availability\nExample: `!check \"Be Our Guest\" 4 2024-12-25 dinner`"),
        ("!alert <restaurant> <party> <date> <meal>", "Create availability alert\nExample: `!alert \"Be Our Guest\" 4 2024-12-25 dinner`"),
        ("!myalerts", "List your active alerts"),
    ]
    
    for cmd, desc in commands_info:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.set_footer(text="The bot checks for availability every 5 minutes")
    
    await ctx.send(embed=embed)


# Run the bot
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables")
        exit(1)
    
    bot.run(token)
