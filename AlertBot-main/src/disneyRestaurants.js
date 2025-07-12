import fetch from 'node-fetch';
import { getCookies } from './disneyAuth.js';

export async function fetchRestaurants(location) {
  const cookies = await getCookies();
  const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');
  const url = `https://disneyworld.disney.go.com/dine-res/api/menu/locations/${encodeURIComponent(location)}`;
  const res = await fetch(url, {
    headers: {
      'cookie': cookieHeader,
      'User-Agent': 'Mozilla/5.0',
      'Accept': 'application/json'
    }
  });
  if (!res.ok) throw new Error(`Disney API error ${res.status}`);
  const data = await res.json();
  return data.restaurants || [];
}
