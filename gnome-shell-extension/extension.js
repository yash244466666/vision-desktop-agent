/*
 * Screenshot Service for Vision Agent — GNOME Shell Extension v5
 *
 * Provides a DBus method to take screenshots from INSIDE the GNOME compositor.
 * This is the ONLY reliable way to capture the screen on GNOME Wayland,
 * since all X11-based and Portal methods produce black frames or are denied.
 *
 * DBus Interface: org.hermes.Screenshot
 * Object Path:    /org/hermes/Screenshot
 * Methods:
 *   Ping()        → (s:reply)         — Health check, returns 'pong'
 *   Capture(s:path) → (b:success, s:info) — Take screenshot, save to path
 *
 * GNOME 49 API: Shell.Screenshot(include_cursor, GOutputStream, callback)
 *   — 2nd arg is GOutputStream (NOT boolean flash like older versions)
 *   — Use Gio.File.new_for_path(path).replace() to create the stream
 *
 * CRITICAL: Do NOT call UninstallExtension DBus method — it deletes extension files!
 * After editing, logout/login is required to reload (Shell caches old code).
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const DBUS_IFACE_XML = `
<node>
  <interface name='org.hermes.Screenshot'>
    <method name='Ping'>
      <arg type='s' direction='out' name='reply'/>
    </method>
    <method name='Capture'>
      <arg type='s' direction='in' name='path'/>
      <arg type='b' direction='out' name='success'/>
      <arg type='s' direction='out' name='info'/>
    </method>
  </interface>
</node>`;

export default class ScreenshotServiceExtension {
  enable() {
    this._busId = Gio.bus_own_name(
      Gio.BusType.SESSION,
      'org.hermes.Screenshot',
      Gio.BusNameOwnerFlags.NONE,
      (connection, name) => {
        // on_bus_acquired — register DBus object here
        let ifaceInfo = Gio.DBusInterfaceInfo.new_for_xml(DBUS_IFACE_XML);

        let regId = connection.register_object(
          '/org/hermes/Screenshot',
          ifaceInfo,
          (connection, sender, path, iface, method, params, invocation) => {
            // method_call handler
            if (method === 'Ping') {
              invocation.return_value(new GLib.Variant('(s)', ['pong']));
            }
            else if (method === 'Capture') {
              let [filePath] = params.deep_unpack();
              try {
                let file = Gio.File.new_for_path(filePath);
                let stream = file.replace(null, false,
                  Gio.FileCreateFlags.REPLACE_DESTINATION, null);

                // GNOME 49: Shell.Screenshot(include_cursor, GOutputStream, callback)
                global.screenshot.screenshot(
                  true,  // include cursor
                  stream,
                  (shell, result) => {
                    try {
                      let success = global.screenshot.screenshot_finish(result);
                      stream.close(null);
                      if (success) {
                        invocation.return_value(
                          new GLib.Variant('(bs)', [true, 'Screenshot saved to ' + filePath])
                        );
                      } else {
                        invocation.return_value(
                          new GLib.Variant('(bs)', [false, 'Shell.Screenshot returned false'])
                        );
                      }
                    } catch (e) {
                      stream.close(null);
                      invocation.return_value(
                        new GLib.Variant('(bs)', [false, 'screenshot_finish error: ' + e.message])
                      );
                    }
                  }
                );
              } catch (e) {
                invocation.return_value(
                  new GLib.Variant('(bs)', [false, 'Capture error: ' + e.message])
                );
              }
            }
          },
          null,  // get_property — not needed
          null    // set_property — not needed
        );

        this._regId = regId;
        log(`[hermes-screenshot] Extension loaded. Object registered (id=${regId})`);
      },
      (connection, name) => {
        // on_name_acquired
        log(`[hermes-screenshot] DBus name 'org.hermes.Screenshot' acquired`);
      },
      (connection, name) => {
        // on_name_lost
        log(`[hermes-screenshot] DBus name lost`);
      }
    );
  }

  disable() {
    if (this._regId) {
      // Note: We need the connection to unregister, but we can get it from the bus
      try {
        let conn = Gio.bus_get_sync(Gio.BusType.SESSION, null);
        conn.unregister_object(this._regId);
      } catch (e) {
        log(`[hermes-screenshot] unregister error: ${e.message}`);
      }
    }
    if (this._busId) {
      Gio.bus_unown_name(this._busId);
    }
    this._regId = null;
    this._busId = null;
    log(`[hermes-screenshot] Extension disabled`);
  }
}