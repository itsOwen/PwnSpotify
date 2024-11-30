from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import pwnagotchi.plugins as plugins
import logging
import requests
import time
import base64
import json
from requests.exceptions import RequestException

class PwnSpotify(plugins.Plugin):
    __author__ = 'itsOwen'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'Shows currently playing Spotify track with scrolling animation'
    __defaults__ = {
        'enabled': False,
        'client_id': '',
        'client_secret': '',
        'redirect_uri': 'http://localhost:8080',
        'scroll_speed': 2,
        'check_interval': 30,
        'auth_code': None,
        'retry_interval': 5,
        'token_file': '/root/.spotify_tokens',
        'display_position': (8, 90),
        'display_width': 12,
        'static_display_time': 3
    }

    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.last_known_song = "Waiting for track..."
        self.scroll_position = 0
        self.last_check = 0
        self.last_retry = 0
        self.ready = False
        self.connection_established = False
        self.last_static_time = 0
        super().__init__()

    def on_loaded(self):
        logging.info("[pwnspotify] Plugin loaded.")
        self.ready = True
        if self._load_saved_tokens():
            self.connection_established = True
        else:
            self.last_retry = 0

    def _load_saved_tokens(self):
        try:
            with open(self.options['token_file'], 'r') as f:
                tokens = json.load(f)
                self.access_token = tokens.get('access_token')
                self.refresh_token = tokens.get('refresh_token')
                logging.info("[pwnspotify] Loaded saved tokens successfully")
                return True
        except (FileNotFoundError, json.JSONDecodeError):
            logging.info("[pwnspotify] No saved tokens found or invalid format")
            return False

    def _try_connection(self):
        current_time = time.time()
        
        if current_time - self.last_retry < self.options['retry_interval']:
            return False

        self.last_retry = current_time
        logging.info("[pwnspotify] Attempting to connect...")

        if self.access_token:
            try:
                response = requests.get(
                    "https://api.spotify.com/v1/me/player/currently-playing",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    timeout=5
                )
                if response.status_code != 401:
                    self.connection_established = True
                    return True
                if self.refresh_access_token():
                    self.connection_established = True
                    return True
            except RequestException:
                logging.info("[pwnspotify] Connection test failed, will retry...")
                return False

        if self.options['auth_code'] and not self.access_token:
            if self.get_tokens(self.options['auth_code']):
                self.connection_established = True
                return True

        return False

    def on_ui_setup(self, ui):
        try:
            ui.remove_element('pwnspotify')
        except:
            pass

        ui.add_element('pwnspotify', 
                      Text(color=BLACK,
                           value=self.last_known_song,
                           position=self.options['display_position'],
                           font=fonts.Medium))

    def on_unload(self, ui):
        try:
            with ui._lock:
                ui.remove_element('pwnspotify')
        except:
            pass

    def on_ui_update(self, ui):
        if not self.ready:
            return

        current_time = time.time()

        if not self.connection_established:
            self._try_connection()
            ui.set('pwnspotify', "Connecting to Spotify...")
            return

        if current_time - self.last_check >= self.options['check_interval']:
            self.last_check = current_time
            self.get_current_track()
            
        scrolling_text = self.get_scrolling_text(self.last_known_song)
        ui.set('pwnspotify', scrolling_text)

    def get_tokens(self, auth_code):
        token_url = "https://accounts.spotify.com/api/token"
        
        auth_header = base64.b64encode(
            f"{self.options['client_id']}:{self.options['client_secret']}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.options['redirect_uri']
        }
        
        try:
            response = requests.post(token_url, headers=headers, data=data, timeout=5)
            if response.status_code == 200:
                tokens = response.json()
                self.access_token = tokens["access_token"]
                self.refresh_token = tokens["refresh_token"]
                logging.info("[pwnspotify] Successfully got access token")
                
                try:
                    with open(self.options['token_file'], 'w') as f:
                        json.dump({
                            'access_token': self.access_token,
                            'refresh_token': self.refresh_token
                        }, f)
                    logging.info("[pwnspotify] Tokens saved successfully")
                except Exception as e:
                    logging.error(f"[pwnspotify] Failed to save tokens: {e}")
                    
                return True
            else:
                logging.error(f"[pwnspotify] Token exchange failed: {response.text}")
                return False
        except RequestException as e:
            logging.error(f"[pwnspotify] Network error during token exchange: {e}")
            return False
        except Exception as e:
            logging.error(f"[pwnspotify] Token exchange error: {e}")
            return False

    def refresh_access_token(self):
        if not self.refresh_token:
            return False
            
        token_url = "https://accounts.spotify.com/api/token"
        
        auth_header = base64.b64encode(
            f"{self.options['client_id']}:{self.options['client_secret']}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        
        try:
            response = requests.post(token_url, headers=headers, data=data, timeout=5)
            if response.status_code == 200:
                tokens = response.json()
                self.access_token = tokens["access_token"]
                if "refresh_token" in tokens:
                    self.refresh_token = tokens["refresh_token"]
                    with open(self.options['token_file'], 'w') as f:
                        json.dump({
                            'access_token': self.access_token,
                            'refresh_token': self.refresh_token
                        }, f)
                logging.info("[pwnspotify] Successfully refreshed access token")
                return True
            else:
                logging.error(f"[pwnspotify] Token refresh failed: {response.text}")
                return False
        except RequestException as e:
            logging.error(f"[pwnspotify] Network error during token refresh: {e}")
            return False
        except Exception as e:
            logging.error(f"[pwnspotify] Token refresh error: {e}")
            return False

    def get_current_track(self):
        if not self.connection_established:
            return "Connecting to Spotify..."

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        
        try:
            response = requests.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                if response.text:
                    data = response.json()
                    if data and data.get('item'):
                        track = data['item']['name']
                        artist = data['item']['artists'][0]['name']
                        self.last_known_song = f"♫ {track} - {artist}"
            elif response.status_code == 401:
                if self.refresh_access_token():
                    return self.get_current_track()
                else:
                    self.connection_established = False
            elif response.status_code == 204:
                self.last_known_song = "No track playing"
            else:
                logging.error(f"[pwnspotify] Unexpected status code: {response.status_code}")
                self.connection_established = False
        except RequestException as e:
            logging.error(f"[pwnspotify] Network error during track fetch: {e}")
            self.connection_established = False
        except Exception as e:
            logging.error(f"[pwnspotify] Track fetch error: {e}")
            self.connection_established = False
            
        return self.last_known_song

    def get_scrolling_text(self, text, width=None):
        if width is None:
            width = self.options['display_width']
            
        if not text:
            return "No track playing"
        
        if not hasattr(self, 'last_static_time'):
            self.last_static_time = 0
            
        if not hasattr(self, 'show_full_text'):
            self.show_full_text = False
            
        current_time = time.time()
        
        if self.show_full_text:
            if current_time - self.last_static_time > self.options['static_display_time']:
                self.show_full_text = False
                self.scroll_position = 0
            else:
                return text
        
        padded_text = text + " " * width
        scroll_text = padded_text[self.scroll_position:self.scroll_position + width]
        
        if self.scroll_position >= len(padded_text) - width:
            self.show_full_text = True
            self.last_static_time = current_time
            self.scroll_position = 0
            return text
        
        self.scroll_position += self.options['scroll_speed']
        return scroll_text.ljust(width)