# Memory Self-Heal Script

## Usage

Run manually:
```bash
sudo ./memory-heal.sh
```

Run via cron (every 5 minutes):
```bash
sudo crontab -e
# Add: */5 * * * * /path/to/memory-heal.sh
```

## What It Does

1. **Monitors** memory usage percentage
2. **Clears cache** (page cache, dentries, inodes) if usage ≥ 85%
3. **Kills top consumer** if still above threshold after cache clear
4. **Logs** all actions to `/var/log/memory-heal.log`

## Configuration

- `THRESHOLD=85` - Memory usage percentage trigger (default: 85%)
- `LOG` - Log file path (default: `/var/log/memory-heal.log`)

## Requirements

- Root/sudo access
- Bash shell
- Standard Linux utilities (free, ps, awk)
