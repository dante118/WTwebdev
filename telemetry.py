'''
Module to query and access telemetry data during War Thunder matches
'''


import socket
from requests import get
from requests.exceptions import ConnectTimeout
from WTwebdev import mapinfo


# IP_ADDRESS     = socket.gethostbyname(socket.gethostname())
IP_ADDRESS   = "127.0.0.1"
URL_INDICATORS = 'http://{}:8111/indicators'.format(IP_ADDRESS)
URL_STATE      = 'http://{}:8111/state'.format(IP_ADDRESS)
URL_COMMENTS   = 'http://{}:8111/gamechat?lastId={}'
URL_EVENTS     = 'http://{}:8111/hudmsg?lastEvt=-1&lastDmg={}'
FT_TO_M        = 0.3048
METRICS_PLANES = ['p-', 'f-', 'f2', 'f3', 'f4', 'f6', 'f7', 'f8', 'f9', 'os',
                  'sb', 'tb', 'a-', 'pb', 'am', 'ad', 'fj', 'b-', 'b_', 'xp',
                  'bt', 'xa', 'xf', 'sp', 'hu', 'ty', 'fi', 'gl', 'ni', 'fu',
                  'fu', 'se', 'bl', 'be', 'su', 'te', 'st', 'mo', 'we', 'ha']

class Status:
    IN_FLIGHT      = 0
    IN_MENU        = -1
    NO_MISSION     = -2
    WT_NOT_RUNNING = -3
    OTHER_ERROR    = -4


def combine_dicts(to_dict: dict, from_dict: dict) -> dict:
    '''
    Merges all contents of "from_dict" into "to_dict"
    
    Args:
        to_dict:
            One dictionary to be merged
        from_dict:
            Other dictionary to be merged
    
    Returns:
            Dictionary with the merged contents of the original to_dict and
            from_dict
    '''
    
    if (type(to_dict) == dict) and (type(from_dict) == dict):
        for key in from_dict.keys():
            to_dict[key] = from_dict[key]

        return to_dict
    else:
        return {}


class TelemInterface(object):
    def __init__(self):
        self.connected       = False
        self.full_telemetry  = {}
        self.basic_telemetry = {}
        self.indicators      = {}
        self.state           = {}
        self.map_info        = mapinfo.MapInfo()
        self.last_event_ID   = -1
        self.last_comment_ID = -1
        self.comments        = []
        self.events          = []
        self.status          = Status.WT_NOT_RUNNING
    
    def get_comments(self) -> list:
        '''
        Query http://localhost:8111/gamechat?lastId=-1 to get a list of all
        comments (in JSON format) made in the current match
        
        Returns:
                List of comments
        '''
        
        comments_response = get(URL_COMMENTS.format(IP_ADDRESS, self.last_comment_ID))
        self.comments.extend(comments_response.json())
        if self.comments:
            self.last_comment_ID = max([comment['id'] for comment in self.comments])
        return self.comments
    
    def get_events(self) -> list:
        '''
        Query http://localhost:8111/hudmsg?lastEvt=-1&lastDmg=-1 to get
        information on all events (i.e. when someone is damaged or destroyed)
        in the current match
        
        Returns:
                Events log dictionary
        '''
        try:
            events_response = get(URL_EVENTS.format(IP_ADDRESS, self.last_event_ID))
            self.events.extend(events_response.json()['damage'])
        except Exception: pass

        
        try:
            self.last_event_ID = self.events[-1]['id']
        except IndexError: pass
        
        return self.events
    
    def find_altitude(self) -> float:
        '''
        Finds and standardizes reported alittude to meters for all planes
        
        Returns:
                Altitude in meters
        '''
        
        name = self.indicators['type']
        
        # account for freedom units in US and UK planes
        if name[:2] in METRICS_PLANES:
            if 'altitude_10k' in self.indicators.keys():
                return self.indicators['altitude_10k'] * FT_TO_M
            elif 'altitude_hour' in self.indicators.keys():
                return self.indicators['altitude_hour'] * FT_TO_M
            elif 'altitude_min' in self.indicators.keys():
                return self.indicators['altitude_min'] * FT_TO_M
            else:
                return 0
        else:
            if 'altitude_10k' in self.indicators.keys():
                return self.indicators['altitude_10k']
            elif 'altitude_hour' in self.indicators.keys():
                return self.indicators['altitude_hour']
            elif 'altitude_min' in self.indicators.keys():
                return self.indicators['altitude_min']
            else:
                return 0

    def get_telemetry(self, comments: bool = False, events: bool = False) -> bool:
        '''
        Ping http://localhost:8111/indicators and http://localhost:8111/state
        to sample telemetry data. Each one of the URL requests returns a
        respective JSON string. These two JSON strings are converted into
        dictionaries (self.indicators and self.state). From these dictionaries,
        two more dictionaries are created: self.full_telemetry and
        self.basic_telemetry.
        
        Dictionary self.full_telemetry holds a combination of all telemetry
        values returned from http://localhost:8111/indicators and
        http://localhost:8111/state. Dictionary self.basic_telemetry holds
        the minimal amount of telmetry needed for navigation and control (see
        file docstring for more info)
        
        Args:
            comments:
                Whether or not to query for match comment data
            events:
                Whether or not to query for match event data
        
        Returns:
                Whether or not player is in a match
        '''
        
        self.connected       = False
        self.full_telemetry  = {}
        self.basic_telemetry = {}

        try:
            self.map_info.download_files()
            self.map_info.parse_meta()
            
            indicator_response = get(URL_INDICATORS)
            self.indicators    = indicator_response.json()

            state_response = get(URL_STATE)
            self.state     = state_response.json()
            
            if comments:
                self.get_comments()
            else:
                self.comments = []
            
            if events:
                self.get_events()
            else:
                self.events = {}

            if self.indicators['valid'] and self.state['valid']:
                try:
                    # fix odd WT sign conventions
                    try:
                        self.indicators['aviahorizon_pitch'] = -self.indicators['aviahorizon_pitch']
                    except KeyError:
                        self.indicators['aviahorizon_pitch'] = 0
                    
                    try:
                        self.indicators['aviahorizon_roll']  = -self.indicators['aviahorizon_roll']
                    except KeyError:
                        self.indicators['aviahorizon_roll']  = 0
                    
                    self.indicators['alt_m'] = self.find_altitude()
                    
                    self.full_telemetry = combine_dicts(self.full_telemetry, self.indicators)
                    self.full_telemetry = combine_dicts(self.full_telemetry, self.state)
                    
                    self.basic_telemetry['airframe'] = self.indicators['type']
                    self.basic_telemetry['roll']     = self.indicators['aviahorizon_roll']
                    self.basic_telemetry['pitch']    = self.indicators['aviahorizon_pitch']
                    # self.basic_telemetry['heading']  = self.indicators['compass']
                    self.basic_telemetry['altitude'] = self.indicators['alt_m']
                
                    self.basic_telemetry['lat'] = self.map_info.player_lat
                    self.full_telemetry['lat']  = self.map_info.player_lat
                    self.basic_telemetry['lon'] = self.map_info.player_lon
                    self.full_telemetry['lon']  = self.map_info.player_lon
                    
                    try: 
                        self.basic_telemetry['IAS'] = self.state['IAS, km/h']
                    except KeyError:
                        self.basic_telemetry['IAS'] = None
                    
                    try: 
                        self.basic_telemetry['flapState'] = self.state['flaps, %']
                    except KeyError:
                        self.basic_telemetry['flapState'] = None
                    
                    try: 
                        self.basic_telemetry['gearState'] = self.state['gear, %']
                    except KeyError:
                        self.basic_telemetry['gearState'] = None
                    
                    self.connected = True
                    self.status    = Status.IN_FLIGHT
                    
                except (KeyError, AttributeError):
                    self.status = Status.IN_MENU
            else:
                self.status = Status.NO_MISSION

        except Exception as e:
            if 'Failed to establish a new connection' in str(e):
                self.status = Status.WT_NOT_RUNNING
            else:
                import traceback
                traceback.print_exc()
                self.status = Status.OTHER_ERROR
        
        return self.connected

    def get_status(self) -> int:
        '''
        Return game status
        '''


        self.connected       = False
        self.full_telemetry  = {}
        self.basic_telemetry = {}

        try:
            
            if not self.map_info.check_battle():
                return Status.IN_MENU
            
            indicator_response = get(URL_INDICATORS)
            self.indicators    = indicator_response.json()

            state_response = get(URL_STATE)
            self.state     = state_response.json()
            
            self.get_events()
            
            if self.indicators['valid'] and self.state['valid']:
                try:
                                        
                    self.basic_telemetry['airframe'] = self.indicators['type']
                    
                    self.connected = True
                    return Status.IN_FLIGHT
                    
                except (KeyError, AttributeError):
                    return Status.IN_MENU
            else:
                return Status.NO_MISSION

        except ConnectTimeout:
            return Status.WT_NOT_RUNNING

        except Exception as e:
            if 'Failed to establish a new connection' in str(e):
                return Status.WT_NOT_RUNNING
            else:
                import traceback
                traceback.print_exc()
                return Status.OTHER_ERROR
