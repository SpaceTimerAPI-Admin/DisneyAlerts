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
                                locations.append({
                                    'id': location_id,
                                    'name': location_name,
                                    'type': 'park' if any(park in location_name.lower() for park in ['kingdom', 'epcot', 'studios', 'animal']) else 'resort'
                                })
                    else:
                        logger.warning(f"Failed to get dining page: {response.status}")
            except Exception as scrape_error:
                logger.warning(f"Error scraping dining page: {scrape_error}")
            
            # Always use comprehensive Disney locations - every single one
            if len(locations) < 5:
                logger.info("Using comprehensive Disney location list")
                locations = [
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
                    {'id': '80010170', 'name': "Disney's Riviera Resort", 'type': 'resort'},
                    {'id': '80010176', 'name': "Disney's Riviera Resort - DVC", 'type': 'resort'},
                    
                    # Deluxe Villas
                    {'id': '80007622', 'name': "Disney's Grand Floridian Resort & Spa - DVC", 'type': 'resort'},
                    {'id': '80007540', 'name': "Disney's Polynesian Villas & Bungalows", 'type': 'resort'},
                    {'id': '80007669', 'name': "Bay Lake Tower at Disney's Contemporary Resort", 'type': 'resort'},
                    {'id': '80007725', 'name': "Disney's Wilderness Lodge - DVC", 'type': 'resort'},
                    {'id': '80007401', 'name': "Disney's BoardWalk Villas", 'type': 'resort'},
                    {'id': '80007561', 'name': "Disney's Beach Club Villas", 'type': 'resort'},
                    {'id': '80007835', 'name': "Disney's Animal Kingdom Villas - Jambo House", 'type': 'resort'},
                    {'id': '80010201', 'name': "Disney's Animal Kingdom Villas - Kidani Village", 'type': 'resort'},
                    
                    # Moderate Resorts
                    {'id': '80007623', 'name': "Disney's Port Orleans Resort - French Quarter", 'type': 'resort'},
                    {'id': '80007624', 'name': "Disney's Port Orleans Resort - Riverside", 'type': 'resort'},
                    {'id': '80007809', 'name': "Disney's Caribbean Beach Resort", 'type': 'resort'},
                    {'id': '80007810', 'name': "Disney's Coronado Springs Resort", 'type': 'resort'},
                    {'id': '80010162', 'name': "Disney's Art of Animation Resort", 'type': 'resort'},
                    
                    # Value Resorts
                    {'id': '80007813', 'name': "Disney's All-Star Sports Resort", 'type': 'resort'},
                    {'id': '80007814', 'name': "Disney's All-Star Music Resort", 'type': 'resort'},
                    {'id': '80007815', 'name': "Disney's All-Star Movies Resort", 'type': 'resort'},
                    {'id': '80010161', 'name': "Disney's Pop Century Resort", 'type': 'resort'},
                    
                    # Other Resort Areas
                    {'id': '80007816', 'name': "Disney's Fort Wilderness Resort & Campground", 'type': 'resort'},
                    {'id': '80007817', 'name': "Disney's Shades of Green", 'type': 'resort'},
                    
                    # Swan & Dolphin (Partner Hotels)
                    {'id': '80007889', 'name': "Walt Disney World Swan", 'type': 'resort'},
                    {'id': '80007890', 'name': "Walt Disney World Dolphin", 'type': 'resort'},
                    {'id': '80010165', 'name': "Walt Disney World Swan Reserve", 'type': 'resort'},
                    
                    # ESPN Wide World of Sports
                    {'id': '80007818', 'name': "ESPN Wide World of Sports Complex", 'type': 'sports'},
                    
                    # Disney's Typhoon Lagoon & Blizzard Beach
                    {'id': '80007819', 'name': "Disney's Typhoon Lagoon", 'type': 'waterpark'},
                    {'id': '80007820', 'name': "Disney's Blizzard Beach", 'type': 'waterpark'},
                    
                    # Golf Courses
                    {'id': '80007821', 'name': "Disney's Magnolia Golf Course", 'type': 'golf'},
                    {'id': '80007822', 'name': "Disney's Palm Golf Course", 'type': 'golf'},
                    
                    # Transportation & Entertainment District
                    {'id': '80007824', 'name': "Disney's Wedding Pavilion", 'type': 'venue'},
                ]
            
            logger.info(f"Returning {len(locations)} Disney locations")
            return locations
                
        except Exception as e:
            logger.error(f"Error in get_locations: {e}")
            # Return fallback locations even on complete failure
            logger.info("Using fallback locations due to error")
            return [
                # Theme Parks
                {'id': '80007944', 'name': 'Magic Kingdom Park', 'type': 'park'},
                {'id': '80007838', 'name': 'EPCOT', 'type': 'park'},
                {'id': '80007998', 'name': "Disney's Hollywood Studios", 'type': 'park'},
                {'id': '80007823', 'name': "Disney's Animal Kingdom Theme Park", 'type': 'park'},
                
                # Disney Springs
                {'id': '80007875', 'name': 'Disney Springs', 'type': 'shopping'},
                
                # Major Deluxe Resorts
                {'id': '80007617', 'name': "Disney's Grand Floridian Resort & Spa", 'type': 'resort'},
                {'id': '80007539', 'name': "Disney's Polynesian Village Resort", 'type': 'resort'},
                {'id': '80007668', 'name': "Disney's Contemporary Resort", 'type': 'resort'},
                {'id': '80007560', 'name': "Disney's Yacht Club Resort", 'type': 'resort'},
                {'id': '80007559', 'name': "Disney's Beach Club Resort", 'type': 'resort'},
                {'id': '80007400', 'name': "Disney's BoardWalk Inn", 'type': 'resort'},
                {'id': '80007724', 'name': "Disney's Wilderness Lodge", 'type': 'resort'},
                {'id': '80007834', 'name': "Disney's Animal Kingdom Lodge", 'type': 'resort'}
            ]
    
    async def get_restaurants(self, location_id: str) -> List[Dict]:
        """Get restaurants using Disney's facility service API"""
        try:
            if not self.session:
                await self.create_session()
            
            restaurants = []
            
            # Use Disney's actual facility service API
            api_url = f"{self.facility_api_url}?locationId={location_id}&language=en_US"
            
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
            
            logger.info(f"Calling Disney API: {api_url}")
            
            try:
                async with self.session.get(api_url, headers=headers) as response:
                    logger.info(f"Disney API response status: {response.status}")
                    
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.info(f"API response type: {type(data)}")
                            
                            # Parse the Disney API response
                            if isinstance(data, dict):
                                # Look for common response structures
                                facilities = data.get('facilities', data.get('dining', data.get('results', [])))
                                
                                if isinstance(facilities, list):
                                    for facility in facilities:
                                        if isinstance(facility, dict):
                                            # Extract restaurant data from Disney's response
                                            restaurant_id = facility.get('id') or facility.get('facilityId') or facility.get('contentId')
                                            restaurant_name = facility.get('name') or facility.get('title')
                                            
                                            # Look for dining-specific facilities
                                            facility_type = facility.get('type', '').lower()
                                            if 'dining' in facility_type or 'restaurant' in facility_type or not facility_type:
                                                
                                                if restaurant_name and restaurant_id:
                                                    # Extract additional details
                                                    cuisine_type = facility.get('cuisineType', facility.get('cuisine', 'Various'))
                                                    meal_periods = facility.get('mealPeriods', facility.get('meals', ['Breakfast', 'Lunch', 'Dinner']))
                                                    
                                                    # Check if it accepts reservations
                                                    accepts_reservations = facility.get('acceptsReservations', 
                                                                                     facility.get('reservationRequired', 
                                                                                     facility.get('bookable', True)))
                                                    
                                                    restaurants.append({
                                                        'id': str(restaurant_id),
                                                        'name': restaurant_name,
                                                        'location_id': location_id,
                                                        'cuisine_type': cuisine_type,
                                                        'meal_periods': meal_periods if isinstance(meal_periods, list) else ['Breakfast', 'Lunch', 'Dinner'],
                                                        'accepts_reservations': bool(accepts_reservations)
                                                    })
                                
                                elif isinstance(data, list):
                                    # If the response is directly a list
                                    for facility in data:
                                        if isinstance(facility, dict):
                                            restaurant_id = facility.get('id') or facility.get('facilityId')
                                            restaurant_name = facility.get('name') or facility.get('title')
                                            
                                            if restaurant_name and restaurant_id:
                                                restaurants.append({
                                                    'id': str(restaurant_id),
                                                    'name': restaurant_name,
                                                    'location_id': location_id,
                                                    'cuisine_type': facility.get('cuisineType', 'Various'),
                                                    'meal_periods': facility.get('mealPeriods', ['Breakfast', 'Lunch', 'Dinner']),
                                                    'accepts_reservations': facility.get('acceptsReservations', True)
                                                })
                            
                            # Filter only restaurants that accept reservations
                            reservation_restaurants = [r for r in restaurants if r['accepts_reservations']]
                            
                            logger.info(f"Found {len(reservation_restaurants)} reservable restaurants from Disney API")
                            
                            if reservation_restaurants:
                                return reservation_restaurants[:25]  # Discord limit
                            
                        except json.JSONDecodeError as json_error:
                            logger.error(f"Failed to parse Disney API JSON: {json_error}")
                            # Disney returned HTML instead of JSON - try to parse HTML
                            response_text = await response.text()
                            logger.info(f"Disney API returned HTML, attempting to parse...")
                            
                            # Parse HTML response for restaurant data
                            try:
                                soup = BeautifulSoup(response_text, 'html.parser')
                                
                                # Look for restaurant data in various HTML structures
                                restaurant_elements = soup.find_all(['div', 'article', 'li'], 
                                                                   class_=re.compile(r'restaurant|dining|facility|card', re.I))
                                
                                for element in restaurant_elements:
                                    # Try to extract restaurant name and ID from HTML
                                    name_elem = element.find(['h1', 'h2', 'h3', 'h4', 'a'], 
                                                            class_=re.compile(r'title|name|heading', re.I))
                                    
                                    if name_elem:
                                        restaurant_name = name_elem.get_text(strip=True)
                                        
                                        # Look for data attributes or IDs
                                        restaurant_id = (element.get('data-id') or 
                                                       element.get('data-restaurant-id') or 
                                                       element.get('id'))
                                        
                                        if not restaurant_id and name_elem.get('href'):
                                            # Extract ID from URL
                                            url_parts = name_elem.get('href').strip('/').split('/')
                                            if url_parts:
                                                restaurant_id = url_parts[-1]
                                        
                                        if restaurant_name and restaurant_id and len(restaurant_name) > 3:
                                            restaurants.append({
                                                'id': str(restaurant_id),
                                                'name': restaurant_name,
                                                'location_id': location_id,
                                                'cuisine_type': 'Various',
                                                'meal_periods': ['Breakfast', 'Lunch', 'Dinner'],
                                                'accepts_reservations': True
                                            })
                                
                                logger.info(f"Parsed {len(restaurants)} restaurants from HTML")
                                
                            except Exception as html_error:
                                logger.error(f"Failed to parse HTML response: {html_error}")
                                
                            logger.error(f"Response text (first 200 chars): {response_text[:200]}")
                        
                    elif response.status == 401:
                        logger.warning("Disney API returned 401 - need to login first")
                    elif response.status == 403:
                        logger.warning("Disney API returned 403 - access denied")
                    else:
                        logger.warning(f"Disney API returned status {response.status}")
                        response_text = await response.text()
                        logger.debug(f"Response: {response_text[:200]}")
                        
            except Exception as api_error:
                logger.error(f"Error calling Disney API: {api_error}")
            
            # If API call failed, use fallback data
            logger.info(f"Using fallback restaurants for {location_id}")
            fallback_restaurants = self.get_fallback_restaurants(location_id)
            return fallback_restaurants
                
        except Exception as e:
            logger.error(f"Error getting restaurants for {location_id}: {e}")
            return self.get_fallback_restaurants(location_id)
    
    def get_fallback_restaurants(self, location_id: str) -> List[Dict]:
        """Get fallback restaurant data for testing"""
        comprehensive_fallback_data = {
            # Magic Kingdom - Complete Restaurant List
            '80007944': [
                {'id': 'be-our-guest-restaurant', 'name': 'Be Our Guest Restaurant', 'cuisine_type': 'French'},
                {'id': 'cinderella-royal-table', 'name': "Cinderella's Royal Table", 'cuisine_type': 'American'},
                {'id': 'crystal-palace', 'name': 'The Crystal Palace', 'cuisine_type': 'American'},
                {'id': 'jungle-navigation-skipper-canteen', 'name': 'Jungle Navigation Co. LTD Skipper Canteen', 'cuisine_type': 'Pan-Asian'},
                {'id': 'liberty-tree-tavern', 'name': 'Liberty Tree Tavern', 'cuisine_type': 'American'},
                {'id': 'plaza-restaurant', 'name': 'The Plaza Restaurant', 'cuisine_type': 'American'},
                {'id': 'tony-town-square-restaurant', 'name': "Tony's Town Square Restaurant", 'cuisine_type': 'Italian'},
                {'id': 'dole-whip', 'name': 'Aloha Isle', 'cuisine_type': 'Snacks'},
            ],
            
            # EPCOT - Complete Restaurant List
            '80007838': [
                {'id': 'monsieur-paul', 'name': 'Monsieur Paul', 'cuisine_type': 'French'},
                {'id': 'akershus-royal-banquet-hall', 'name': 'Akershus Royal Banquet Hall', 'cuisine_type': 'Norwegian'},
                {'id': 'le-cellier-steakhouse', 'name': 'Le Cellier Steakhouse', 'cuisine_type': 'Canadian'},
                {'id': 'spice-road-table', 'name': 'Spice Road Table', 'cuisine_type': 'Mediterranean'},
                {'id': 'chefs-de-france', 'name': 'Chefs de France', 'cuisine_type': 'French'},
                {'id': 'biergarten-restaurant', 'name': 'Biergarten Restaurant', 'cuisine_type': 'German'},
                {'id': 'san-angel-inn-restaurante', 'name': 'San Angel Inn Restaurante', 'cuisine_type': 'Mexican'},
                {'id': 'teppan-edo', 'name': 'Teppan Edo', 'cuisine_type': 'Japanese'},
                {'id': 'tokyo-dining', 'name': 'Tokyo Dining', 'cuisine_type': 'Japanese'},
                {'id': 'via-napoli-ristorante-e-pizzeria', 'name': 'Via Napoli Ristorante e Pizzeria', 'cuisine_type': 'Italian'},
                {'id': 'garden-grill-restaurant', 'name': 'Garden Grill Restaurant', 'cuisine_type': 'American'},
                {'id': 'coral-reef-restaurant', 'name': 'Coral Reef Restaurant', 'cuisine_type': 'Seafood'},
                {'id': 'space-220-restaurant', 'name': 'Space 220 Restaurant', 'cuisine_type': 'Contemporary'},
            ],
            
            # Hollywood Studios - Complete Restaurant List
            '80007998': [
                {'id': 'hollywood-brown-derby', 'name': 'The Hollywood Brown Derby', 'cuisine_type': 'American'},
                {'id': 'sci-fi-dine-in-theater-restaurant', 'name': 'Sci-Fi Dine-In Theater Restaurant', 'cuisine_type': 'American'},
                {'id': 'mama-melrose-ristorante-italiano', 'name': "Mama Melrose's Ristorante Italiano", 'cuisine_type': 'Italian'},
                {'id': 'oga-cantina', 'name': "Oga's Cantina", 'cuisine_type': 'Star Wars Themed'},
                {'id': 'hollywood-vine', 'name': 'Hollywood & Vine', 'cuisine_type': 'American'},
                {'id': 'prime-time-cafe', 'name': "50's Prime Time Café", 'cuisine_type': 'American'},
                {'id': 'docking-bay-7-food-and-cargo', 'name': 'Docking Bay 7 Food and Cargo', 'cuisine_type': 'Star Wars Themed'},
            ],
            
            # Animal Kingdom - Complete Restaurant List
            '80007823': [
                {'id': 'tiffins', 'name': 'Tiffins', 'cuisine_type': 'International'},
                {'id': 'tusker-house', 'name': 'Tusker House Restaurant', 'cuisine_type': 'African-American'},
                {'id': 'yak-yeti-restaurant', 'name': 'Yak & Yeti Restaurant', 'cuisine_type': 'Asian'},
                {'id': 'rainforest-cafe', 'name': 'Rainforest Cafe', 'cuisine_type': 'American'},
                {'id': 'flame-tree-barbecue', 'name': 'Flame Tree Barbecue', 'cuisine_type': 'Barbecue'},
                {'id': 'satu-li-canteen', 'name': "Satu'li Canteen", 'cuisine_type': 'Pandoran/Healthy'},
            ],
            
            # Disney Springs - Complete Restaurant List
            '80007875': [
                {'id': 'raglan-road', 'name': 'Raglan Road Irish Pub and Restaurant', 'cuisine_type': 'Irish'},
                {'id': 'wine-bar-george', 'name': 'Wine Bar George', 'cuisine_type': 'Wine Bar'},
                {'id': 'the-boathouse', 'name': 'The BOATHOUSE', 'cuisine_type': 'Seafood'},
                {'id': 'chef-art-smiths-homecomin', 'name': "Chef Art Smith's Homecomin'", 'cuisine_type': 'Southern'},
                {'id': 'morimoto-asia', 'name': 'Morimoto Asia', 'cuisine_type': 'Pan-Asian'},
                {'id': 'city-works-eatery-pour-house', 'name': 'City Works Eatery & Pour House', 'cuisine_type': 'American'},
                {'id': 'wolfgang-puck-bar-grill', 'name': 'Wolfgang Puck Bar & Grill', 'cuisine_type': 'Contemporary'},
                {'id': 'amorettes-patisserie', 'name': "Amorette's Patisserie", 'cuisine_type': 'French Pastries'},
                {'id': 'gideons-bakehouse', 'name': "Gideon's Bakehouse", 'cuisine_type': 'Bakery'},
            ],
            
            # Grand Floridian - Complete Restaurant List
            '80007617': [
                {'id': 'victoria-alberts', 'name': "Victoria & Albert's", 'cuisine_type': 'Contemporary American'},
                {'id': 'citricos', 'name': 'Citricos', 'cuisine_type': 'Contemporary American'},
                {'id': 'narcoossee', 'name': "Narcoossee's", 'cuisine_type': 'Seafood'},
                {'id': '1900-park-fare', 'name': '1900 Park Fare', 'cuisine_type': 'American'},
                {'id': 'grand-floridian-cafe', 'name': 'Grand Floridian Café', 'cuisine_type': 'American'},
            ],
            
            # Contemporary Resort - Complete Restaurant List
            '80007668': [
                {'id': 'california-grill', 'name': 'California Grill', 'cuisine_type': 'Contemporary American'},
                {'id': 'chef-mickeys', 'name': "Chef Mickey's", 'cuisine_type': 'American'},
                {'id': 'steakhouse-71', 'name': 'Steakhouse 71', 'cuisine_type': 'Steakhouse'},
                {'id': 'the-wave-restaurant-of-american-flavors', 'name': 'The Wave... of American Flavors', 'cuisine_type': 'Contemporary American'},
            ],
            
            # Polynesian Village Resort - Complete Restaurant List
            '80007539': [
                {'id': 'ohana', 'name': "'Ohana", 'cuisine_type': 'Polynesian'},
                {'id': 'kona-cafe', 'name': 'Kona Cafe', 'cuisine_type': 'Pacific Rim'},
                {'id': 'trader-sams-grog-grotto', 'name': "Trader Sam's Grog Grotto", 'cuisine_type': 'Polynesian/Tiki'},
                {'id': 'capt-cooks', 'name': "Capt. Cook's", 'cuisine_type': 'Quick Service'},
            ],
        }
        
        # If no restaurant data for this location, create generic ones
        if not restaurants:
            restaurants = [
                {'id': f'{location_id}-signature-dining', 'name': f'Signature Dining at {location_id}', 'cuisine_type': 'Fine Dining'},
                {'id': f'{location_id}-table-service', 'name': f'Table Service Restaurant at {location_id}', 'cuisine_type': 'American'},
                {'id': f'{location_id}-quick-service', 'name': f'Quick Service at {location_id}', 'cuisine_type': 'Quick Service'}
            ]
        
        # Format for consistency
        formatted_restaurants = []
        for restaurant in restaurants:
            formatted_restaurants.append({
                'id': restaurant['id'],
                'name': restaurant['name'],
                'location_id': location_id,
                'cuisine_type': restaurant['cuisine_type'],
                'meal_periods': ['Breakfast', 'Lunch', 'Dinner'],
                'accepts_reservations': True
            })
        
        return formatted_restaurants
    
    async def check_availability(self, restaurant_id: str, party_size: int, date: str, meal_period: str) -> List[Dict]:
        """Check real availability using Disney's restaurant availability API"""
        try:
            if not self.session:
                await self.create_session()
            
            # Format date for Disney's API (YYYY-MM-DD format)
            search_date = date  # Already in correct format from user input
            
            # Convert meal period to Disney's expected format
            meal_period_upper = meal_period.upper()
            
            # Get ALL Disney location IDs to try for restaurant availability
            all_location_ids = [
                # Theme Parks
                '80007944',  # Magic Kingdom
                '80007838',  # EPCOT
                '80007998',  # Hollywood Studios
                '80007823',  # Animal Kingdom
                
                # Disney Springs
                '80007875',  # Disney Springs
                
                # Deluxe Resorts
                '80007617',  # Grand Floridian
                '80007539',  # Polynesian Village
                '80007668',  # Contemporary
                '80007560',  # Yacht Club
                '80007559',  # Beach Club
                '80007400',  # BoardWalk Inn
                '80007724',  # Wilderness Lodge
                '80007834',  # Animal Kingdom Lodge
                '80010170',  # Riviera Resort
                
                # Deluxe Villas
                '80007622',  # Grand Floridian DVC
                '80007540',  # Polynesian Villas
                '80007669',  # Bay Lake Tower
                '80007725',  # Wilderness Lodge DVC
                '80007401',  # BoardWalk Villas
                '80007561',  # Beach Club Villas
                '80007835',  # Animal Kingdom Villas - Jambo
                '80010201',  # Animal Kingdom Villas - Kidani
                
                # Moderate Resorts
                '80007623',  # Port Orleans French Quarter
                '80007624',  # Port Orleans Riverside
                '80007809',  # Caribbean Beach
                '80007810',  # Coronado Springs
                '80010162',  # Art of Animation
                
                # Value Resorts
                '80007813',  # All-Star Sports
                '80007814',  # All-Star Music
                '80007815',  # All-Star Movies
                '80010161',  # Pop Century
                
                # Other Locations
                '80007816',  # Fort Wilderness
                '80007889',  # Swan
                '80007890',  # Dolphin
                '80010165',  # Swan Reserve
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
                    
                    api_url = f"{self.availability_api_url}?" + "&".join([f"{k}={v}" for k, v in params.items()])
                    logger.info(f"Checking availability: {api_url}")
                    
                    async with self.session.get(self.availability_api_url, params=params, headers=headers) as response:
                        logger.info(f"Availability API response status for location {location_id}: {response.status}")
                        
                        if response.status == 200:
                            try:
                                data = await response.json()
                                logger.info(f"Availability API response type: {type(data)}")
                                
                                # Parse availability data from Disney's response
                                if isinstance(data, dict):
                                    # Look for availability data in different possible structures
                                    availability_data = (data.get('availability') or 
                                                       data.get('restaurants') or 
                                                       data.get('results') or 
                                                       data.get('offers') or 
                                                       data.get('times') or 
                                                       [])
                                    
                                    if isinstance(availability_data, list):
                                        for item in availability_data:
                                            if isinstance(item, dict):
                                                # Check if this item is for our target restaurant
                                                item_restaurant_id = (item.get('restaurantId') or 
                                                                    item.get('facilityId') or 
                                                                    item.get('id'))
                                                
                                                if str(item_restaurant_id) == str(restaurant_id):
                                                    # Extract available times
                                                    times = (item.get('availableTimes') or 
                                                           item.get('times') or 
                                                           item.get('slots') or 
                                                           [])
                                                    
                                                    if isinstance(times, list):
                                                        for time_slot in times:
                                                            if isinstance(time_slot, dict):
                                                                time_str = (time_slot.get('time') or 
                                                                          time_slot.get('displayTime') or 
                                                                          time_slot.get('timeSlot'))
                                                                
                                                                if time_str:
                                                                    booking_url = (time_slot.get('bookingUrl') or 
                                                                                 time_slot.get('url') or 
                                                                                 f"{self.base_url}/dining/reservation/{time_slot.get('id', '')}")
                                                                    
                                                                    available_times.append({
                                                                        'time': time_str,
                                                                        'id': time_slot.get('id', ''),
                                                                        'url': booking_url,
                                                                        'restaurant_id': restaurant_id,
                                                                        'location_id': location_id
                                                                    })
                                                            elif isinstance(time_slot, str):
                                                                # Simple time string
                                                                available_times.append({
                                                                    'time': time_slot,
                                                                    'id': f"{restaurant_id}_{time_slot}",
                                                                    'url': f"{self.base_url}/dining/reservation/?restaurant={restaurant_id}&time={time_slot}",
                                                                    'restaurant_id': restaurant_id,
                                                                    'location_id': location_id
                                                                })
                                    
                                    # Also check if the response directly contains availability for any restaurant
                                    elif isinstance(data, list):
                                        for restaurant_data in data:
                                            if isinstance(restaurant_data, dict):
                                                rest_id = (restaurant_data.get('restaurantId') or 
                                                         restaurant_data.get('id'))
                                                
                                                if str(rest_id) == str(restaurant_id):
                                                    times = restaurant_data.get('availableTimes', [])
                                                    for time_str in times:
                                                        available_times.append({
                                                            'time': time_str,
                                                            'id': f"{restaurant_id}_{time_str}",
                                                            'url': f"{self.base_url}/dining/reservation/?restaurant={restaurant_id}&time={time_str}",
                                                            'restaurant_id': restaurant_id,
                                                            'location_id': location_id
                                                        })
                                
                                # If we found availability, break out of the location loop
                                if available_times:
                                    logger.info(f"Found {len(available_times)} available times for restaurant {restaurant_id}")
                                    break
                                    
                            except json.JSONDecodeError as json_error:
                                logger.error(f"Failed to parse availability JSON for location {location_id}: {json_error}")
                                response_text = await response.text()
                                logger.debug(f"Response text: {response_text[:200]}")
                        
                        elif response.status == 401:
                            logger.warning(f"Disney availability API returned 401 for location {location_id} - need authentication")
                        elif response.status == 403:
                            logger.warning(f"Disney availability API returned 403 for location {location_id} - access denied")
                        elif response.status == 404:
                            logger.debug(f"No availability data found for location {location_id}")
                        else:
                            logger.warning(f"Disney availability API returned {response.status} for location {location_id}")
                            
                except Exception as location_error:
                    logger.debug(f"Error checking location {location_id}: {location_error}")
                    continue
            
            if available_times:
                logger.info(f"Total found {len(available_times)} available times for restaurant {restaurant_id}")
                return available_times[:10]  # Limit to first 10 times
            else:
                logger.info(f"No availability found for restaurant {restaurant_id}")
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
        
        # Update database schema to include location_id and restaurant_location_id
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
