# cap_and_analyze.py - Full auto: capture ESP32 + analyze 7-bit frames
# Run: py cap_and_analyze.py
import subprocess, sys, os, time, datetime

DOWNLOADS = os.path.expandvars(r'%USERPROFILE%\Downloads')
ANADIR = os.path.expandvars(r'%USERPROFILE%\iCloudDrive\iCloud~md~obsidian\curryhendry\空调逆向')
ANADIR_OUT = os.path.expandvars(r'%USERPROFILE%\iCloudDrive\iCloud~md~obsidian\curryhendry\空调逆向')

def main():
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    raw_file = os.path.join(DOWNLOADS, f'cap_raw_{ts}.txt')
    
    print('=' * 50)
    print('  AC 30s capture on ESP32 D33')
    print('=' * 50)
    print()
    print('You may press buttons during capture.')
    print('Starting 30s...')
    
    # Run mpremote, capture via subprocess (no shell redirect)
    try:
        result = subprocess.run(
            ['mpremote', 'connect', 'COM3', 'run', os.path.join(DOWNLOADS, 'esp_btn.py')],
            capture_output=True,
            timeout=90
        )
    except subprocess.TimeoutExpired:
        print('TIMEOUT - ESP32 capture took too long')
        return
    
    raw = result.stdout
    if not raw:
        raw = result.stderr  # mpremote sometimes routes via stderr
    
    # Save raw data
    with open(raw_file, 'w', encoding='utf-8') as f:
        f.write(raw.decode('utf-8', errors='replace'))
    
    lines = [l for l in raw.decode('utf-8', errors='replace').split('\n') if l.strip()]
    print(f'\nDone. {len(lines)} edges captured.')
    print(f'Raw saved: {raw_file}')
    
    # Run analyzer
    sys.path.insert(0, ANADIR)
    from auto_analyze import analyze
    
    result = analyze(raw_file, f'capture_{ts}')
    print(result)
    
    # Save analysis
    analysis_file = raw_file.replace('.txt', '_analysis.txt')
    with open(analysis_file, 'w', encoding='utf-8') as f:
        f.write(result)
    print(f'\nAnalysis saved: {analysis_file}')

if __name__ == '__main__':
    main()
