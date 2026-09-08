#!/usr/bin/env node
// Ein – Wear the Escape: Promo Video Generator
// Calls Muapi image-to-video API for each scene.
// Usage (t2v preview mode): node scripts/generate_promo.js
// Usage (i2v with local images): node scripts/generate_promo.js --i2v

import { readFileSync, existsSync, mkdirSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const API_KEY = process.env.MUAPI_KEY || 'a1e0a54fbdfe81fb7f7b35fa170c266fd372fa63145eedaa8491c096aaea7079';
const BASE_URL = 'http://localhost:5173';

const MODEL = 'kling-v3.0-pro-text-to-video';
const I2V_MODEL = 'kling-v3.0-pro-image-to-video';
const ASPECT_RATIO = '9:16';
const DURATION = 5;

const scenes = [
  {
    name: 'out-of-office',
    tagline: 'Out of office.',
    imageFile: 'input_images/scene1.jpg',
    prompt: 'Luxury fashion editorial. Beautiful tanned woman with long dark wet hair, wearing oversized cat-eye sunglasses and a crochet mesh cover-up in terracotta orange, navy blue and sand beige vertical stripes with long fringe hem. Carrying a round woven straw tote bag with leather handles. Walking confidently out of the entrance of a luxury Mediterranean hotel with white stone walls and palm trees, blue Aegean sea and hillside town visible in the background. Warm golden afternoon sunlight casting soft shadows. Elegant slow stride. Cinematic 9:16 vertical. Slow motion. Luxury brand film aesthetic.',
  },
  {
    name: 'booked-the-summer',
    tagline: 'Booked the summer.',
    imageFile: 'input_images/scene2.jpg',
    prompt: 'Luxury lifestyle editorial. Beautiful tanned woman with long dark hair and oversized cat-eye sunglasses, wearing a crochet mesh poncho cover-up in terracotta orange, navy blue and sand beige, seated at a wooden beach club table under a thatched palm canopy. Holding an Aperol spritz in a tall wine glass. A woven straw tote bag with "Marissa" embroidery on the table beside her. Mediterranean coastline and sea visible in background, other guests and palm trees. Sandy beach underfoot. Warm golden afternoon light. Slight smile. Cinematic 9:16 vertical.',
  },
  {
    name: 'the-walk',
    tagline: '',
    imageFile: 'input_images/scene3.jpg',
    prompt: 'Cinematic golden hour. Beautiful tanned woman from behind, walking barefoot along the edge of a Mediterranean beach at sunset. Wearing a flowing crochet mesh cover-up in terracotta orange, navy blue and sand beige with long fringe hem that moves in the breeze. Carrying a round woven straw tote bag. White villas and hillside resort in background. Gentle waves lapping the shoreline. Warm amber and gold sunset sky filling the frame. Film grain. Slow cinematic walk. Hair and fringe moving in soft sea breeze. 9:16 vertical. No text.',
  },
  {
    name: 'made-for-slow-summers',
    tagline: 'Made for slow summers.',
    imageFile: 'input_images/scene4.jpg',
    prompt: 'Fashion editorial close portrait. Beautiful tanned woman with long dark hair, wearing oversized cat-eye sunglasses and a crochet mesh cover-up in terracotta orange, navy blue and sand beige, styled off-shoulder. Holding leather sandals loosely in one hand. Rocky Mediterranean cove with clear turquoise water and pebble beach in soft background. Warm bright Mediterranean sunlight. Hair and crochet fringe moving subtly in breeze. Confident relaxed expression. Cinematic 9:16 vertical.',
  },
  {
    name: 'wear-the-escape',
    tagline: 'Ein – Wear the escape.',
    imageFile: 'input_images/scene5.jpg',
    prompt: 'Luxury brand film finale. Beautiful tanned woman from behind, seated on a weathered wooden dock pier at golden sunset. Wearing a crochet mesh poncho in terracotta orange, navy blue and sand beige with fringe. A sailboat on the glowing amber horizon. An Aperol spritz glass beside her. White villas and hillside in background. She gazes out at the sea, still and contemplative. Warm amber orange sunset light fills the entire frame. Slow cinematic zoom out. 9:16 vertical. Cinematic luxury brand aesthetic.',
  },
];

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function submitJob(endpoint, payload) {
  const res = await fetch(`${BASE_URL}/api/v1/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': API_KEY },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Submit failed ${res.status}: ${txt.slice(0, 300)}`);
  }
  return res.json();
}

async function pollResult(requestId, maxAttempts = 120, interval = 3000) {
  const url = `${BASE_URL}/api/v1/predictions/${requestId}/result`;
  for (let i = 1; i <= maxAttempts; i++) {
    await sleep(interval);
    process.stdout.write(`\r  Polling ${i}/${maxAttempts}...`);
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', 'x-api-key': API_KEY },
    });
    if (!res.ok) continue;
    const data = await res.json();
    const status = data.status?.toLowerCase();
    if (status === 'completed' || status === 'succeeded' || status === 'success') {
      const videoUrl = data.outputs?.[0] || data.url || data.output?.url;
      return videoUrl;
    }
    if (status === 'failed' || status === 'error') {
      throw new Error(`Generation failed: ${data.error || 'unknown'}`);
    }
  }
  throw new Error('Timed out after polling.');
}

function imageToBase64DataUrl(filePath) {
  const abs = join(__dirname, '..', filePath);
  if (!existsSync(abs)) return null;
  const buf = readFileSync(abs);
  const ext = filePath.split('.').pop().toLowerCase();
  const mime = ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg';
  return `data:${mime};base64,${buf.toString('base64')}`;
}

async function run() {
  const useI2V = process.argv.includes('--i2v');
  console.log(`\n🎬 Ein – Wear the Escape | Promo Video Generator`);
  console.log(`Mode: ${useI2V ? 'Image-to-Video (your photos)' : 'Text-to-Video (AI recreation)'}`);
  console.log(`Model: ${useI2V ? I2V_MODEL : MODEL} | 9:16 | 5s\n`);

  const outputDir = join(__dirname, '..', 'output_videos');
  if (!existsSync(outputDir)) mkdirSync(outputDir, { recursive: true });

  const results = [];

  for (const [idx, scene] of scenes.entries()) {
    console.log(`\n[${idx + 1}/5] ${scene.name}${scene.tagline ? ` — "${scene.tagline}"` : ''}`);

    let payload, endpoint;

    if (useI2V) {
      const dataUrl = imageToBase64DataUrl(scene.imageFile);
      if (!dataUrl) {
        console.warn(`  ⚠️  Image not found at ${scene.imageFile} — skipping. Drop your images in input_images/ and re-run with --i2v`);
        continue;
      }
      endpoint = I2V_MODEL;
      payload = {
        prompt: scene.prompt,
        image_url: dataUrl,
        aspect_ratio: ASPECT_RATIO,
        duration: DURATION,
      };
    } else {
      endpoint = MODEL;
      payload = {
        prompt: scene.prompt,
        aspect_ratio: ASPECT_RATIO,
        duration: DURATION,
      };
    }

    try {
      console.log(`  Submitting...`);
      const submit = await submitJob(endpoint, payload);
      const requestId = submit.request_id || submit.id;
      if (!requestId) throw new Error('No request_id in response: ' + JSON.stringify(submit).slice(0, 200));

      console.log(`  Request ID: ${requestId}`);
      const videoUrl = await pollResult(requestId);
      process.stdout.write('\n');
      console.log(`  ✅ Done: ${videoUrl}`);

      results.push({ scene: scene.name, tagline: scene.tagline, url: videoUrl });
    } catch (err) {
      process.stdout.write('\n');
      console.error(`  ❌ Error: ${err.message}`);
      results.push({ scene: scene.name, tagline: scene.tagline, error: err.message });
    }
  }

  // Save results
  const outFile = join(outputDir, 'results.json');
  writeFileSync(outFile, JSON.stringify(results, null, 2));

  console.log('\n\n═══════════════════════════════════');
  console.log('🎬 RESULTS');
  console.log('═══════════════════════════════════');
  results.forEach(r => {
    if (r.url) console.log(`✅ ${r.scene}: ${r.url}`);
    else console.log(`❌ ${r.scene}: ${r.error}`);
  });
  console.log(`\nSaved to: ${outFile}`);
}

run().catch(console.error);
