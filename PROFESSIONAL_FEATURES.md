# Professional deployment and device support

## Included in this version

- Responsive dashboard for phones, tablets, laptops, desktop screens, and capable smartwatch browsers
- Accessible account sign-in, administrator/staff roles, and audit logging
- Batch-level stock control, low-stock alerts, expiry prevention, and FEFO issuing
- USB/Bluetooth barcode scanners, manual barcode entry, and phone-camera barcode scanning
- Optional voice barcode entry, with browser permission
- Progressive-web-app metadata for an installable web experience

## Camera and microphone privacy

The application only requests camera or microphone access after the user presses **Use phone camera** or **Use voice entry**. Modern browsers require a secure HTTPS address for those capabilities, except when running at `localhost` on the same device.

## Reliable online use

Before real-world use, deploy behind HTTPS, set a unique `SECRET_KEY`, disable debug mode, use a managed database with backups, and give each employee their own account. Do not expose the local VS Code development server directly to the public internet.

## Wi-Fi and smartwatch access

For normal dashboard access on shop Wi-Fi, run the app and use the computer's IPv4 address from another device on the same private network. Camera/microphone access requires the HTTPS online deployment. A smartwatch can open the responsive dashboard if it supports modern web browsing. A dedicated native Apple Watch or Wear OS app is a separate platform-specific project that must be built and tested with its watch SDK and hardware.
