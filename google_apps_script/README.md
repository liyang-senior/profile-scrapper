# Apps Script setup

1. **Extensions** → **Apps Script** on your spreadsheet  
2. Paste **Code.gs** → **Save**

## For testing (recommended while you iterate)

1. **Deploy** → **Test deployments** (or **Deploy** → gear → **Test deployments**)  
2. Copy the URL ending in **`/dev`**  
3. Paste into the Python app → **Test Apps Script**

- Uses the **latest saved code** after each Save in the editor  
- You do **not** need a new “version” deployment for every code change  

**Web app settings for /dev:**

- Execute as: **Me**  
- Who has access: **Anyone** (so Python on your PC can POST)

## For production (optional, stable URL)

1. **Deploy** → **New deployment** → **Web app**  
2. Copy URL ending in **`/exec`**  
3. Create a **New version** only when you want to freeze a release  

## Both URLs work

The Python app accepts **`/dev`** and **`/exec`**. Use `/dev` while testing; switch to `/exec` later if you want a fixed deployment.

Keep the URL private — anyone with the link can add rows to your sheet.
