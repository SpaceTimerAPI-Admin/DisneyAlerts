import fs from 'fs';
import fetch from 'node-fetch';

const COOKIE_PATH = './session/cookies.json';
const DINE_API = 'https://disneyworld.disney.go.com/dine-res/api';

function loadCookies() {
  const cookies = JSON.parse(fs.readFileSync(COOKIE_PATH));
  return cookies.map(c => `${c.name}=${c.value}`).join('; ');
}

export async function getLocations() {
  const res = await fetch(`${DINE_API}/locations`, { headers: { cookie: loadCookies() } });
  const data = await res.json();
  return data.map(loc => loc.name);
}

export async function getRestaurantsForLocation(locationName) {
  const res = await fetch(`${DINE_API}/restaurants?location=${encodeURIComponent(locationName)}`, { headers: { cookie: loadCookies() } });
  const data = await res.json();
  return data.map(r => ({ name: r.name, id: r.entityId }));
}

export async function checkAvailability(restaurantId, date, mealPeriod, partySize, user) {
  const mealMap = {
    breakfast: { start: '07:00', end: '10:59' },
    lunch:     { start: '11:00', end: '15:59' },
    dinner:    { start: '16:00', end: '22:00' },
  };
  const times = mealMap[mealPeriod];
  const res = await fetch(`${DINE_API}/availability/${partySize}/${date}?entityId=${restaurantId}`, { headers: { cookie: loadCookies() } });
  const { availability } = await res.json();
  const slot = availability.find(s => s.time >= times.start && s.time <= times.end);
  if (slot) {
    const link = `https://disneyworld.disney.go.com/dine-reservation/${restaurantId}/${date}/${partySize}`;
    await user.send(`🎉 **Availability!** Restaurant: **${restaurantId}**, Date: **${date}**, Time: **${slot.time}**, [Book now](${link})`);
  } else {
    setTimeout(() => checkAvailability(restaurantId, date, mealPeriod, partySize, user), 1000 * 60 * 5);
  }
}