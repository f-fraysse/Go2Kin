# Settings Reference Files

This directory contains settings reference files for different GoPro camera models and firmware versions.

## File Naming Convention

Files are named: `settings_reference_{MODEL}_{FIRMWARE}.json`

Example: `settings_reference_HERO12_Black_H23_01_02_32_00.json`

## How Reference Files Are Generated

Reference files are automatically generated using the `tools/discover_camera_settings.py` script, which:
1. Queries each camera setting with an invalid option (-1)
2. Parses the 403 error response to extract available options
3. Saves the settings and their options to a JSON file

## ⚠️ Known Issue: Truncated Display Names

**The camera's 403 error response truncates some display names**, particularly for resolution options with aspect ratio variants. This causes duplicate names in the reference file.

### Example Problem

The camera returns:
- `"107": "5.3K"` (should be "5.3K 8:7 V2")
- `"108": "4K"` (should be "4K 8:7 V2")
- `"109": "4K"` (should be "4K 9:16 V2")
- `"110": "1080"` (should be "1080 9:16 V2")
- `"111": "2.7K"` (should be "2.7K 4:3 V2")

### Solution: Manual Correction Required

After running the discovery tool, **manually verify and correct** the display names by cross-referencing with the OpenGoPro API documentation:

**For HERO12 Black, the correct Video Resolution options are:**
```json
"100": "5.3K",
"107": "5.3K 8:7 V2",
"1": "4K",
"18": "4K 4:3",
"108": "4K 8:7 V2",
"4": "2.7K",
"111": "2.7K 4:3 V2",
"9": "1080",
"109": "4K 9:16 V2",
"110": "1080 9:16 V2"
```

## Reference Documentation

- OpenGoPro API: https://gopro.github.io/OpenGoPro/
- Settings documentation: https://gopro.github.io/OpenGoPro/http#tag/Query

## For New Camera Models

When adding support for a new camera model:

1. Run the discovery tool:
   ```bash
   python tools/discover_camera_settings.py <serial_number>
   ```

2. **Manually review the generated reference file** for duplicate display names

3. Cross-reference with the OpenGoPro API documentation for your camera model

4. Correct any truncated names (especially resolution options)

5. Test the corrected reference file by connecting the camera and verifying dropdown options

## File Structure

Each reference file contains:
- `metadata`: Camera model, firmware version, discovery date
- `settings`: Dictionary of setting IDs with available options
- `status_names`: Dictionary of status IDs with human-readable names

Example:
```json
{
  "metadata": {
    "camera_model": "HERO12 Black",
    "firmware_version": "H23.01.02.32.00",
    "discovery_date": "2025-11-19T14:42:23.641449",
    "total_settings": 35
  },
  "settings": {
    "2": {
      "name": "Video Resolution",
      "available_options": {
        "100": "5.3K",
        "1": "4K",
        ...
      }
    }
  },
  "status_names": {
    "1": "Battery Present",
    ...
  }
}
