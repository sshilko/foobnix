#-*- coding: utf-8 -*-
'''
Created on 28 сент. 2010

@author: ivan
'''
import gst
import urllib
import os
from foobnix.regui.engine import MediaPlayerEngine
from foobnix.util import LOG
import time
import thread
from foobnix.util.fc import FC
from foobnix.util.const import STATE_STOP, STATE_PLAY, STATE_PAUSE, FTYPE_RADIO
from foobnix.util.plsparser import get_radio_source

class GStreamerEngine(MediaPlayerEngine):
    NANO_SECONDS = 1000000000
    def __init__(self, controls):
        MediaPlayerEngine.__init__(self, controls)

        self.player = self.gstreamer_player()
        self.position_sec = 0
        self.duration_sec = 0

        self.prev_path = None
        self.bean = None
        self.equalizer = None
        
        self.current_state = STATE_STOP
        self.remembered_seek_position = 0

    def get_state(self):
        return self.current_state
    def set_state(self, state):        
        self.current_state = state

    def gstreamer_player(self):
        playbin = gst.element_factory_make("playbin2", "player")
        
        
        if FC().is_eq_enable:
            self.audiobin = gst.Bin('audiobin')
            audiosink = gst.element_factory_make('autoaudiosink', 'audiosink')
    
            self.audiobin.add(audiosink)
            self.audiobin.add_pad(gst.GhostPad('sink', audiosink.get_pad('sink')))
            playbin.set_property('audio-sink', self.audiobin)
            
            self.equalizer = gst.element_factory_make('equalizer-10bands', 'equalizer')
            self.audiobin.add(self.equalizer)
    
            
            self.audiobin.get_pad('sink').set_target(self.equalizer.get_pad('sink'))
            self.equalizer.link(audiosink)
    
        bus = playbin.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect("message", self.on_message)
        bus.connect("sync-message::element", self.on_sync_message)
        LOG.debug("LOCAL gstreamer")
        return playbin
    
    def notify_init(self, duraction_int):
        LOG.debug("Pre init thread", duraction_int)

    def notify_playing(self, position_int, duration_int, sec):
        #LOG.debug("Notify playing", position_int)
        self.position_sec = position_int / self.NANO_SECONDS
        self.duration_sec = duration_int / self.NANO_SECONDS
        self.controls.notify_playing(self.position_sec, self.duration_sec, self.bean, sec)

    def notify_eos(self):
        LOG.debug("Notify eos, STOP State")
        self.controls.notify_eos()
        
        self.set_state(STATE_STOP)

    def notify_title(self, text):
        if self.bean.type == FTYPE_RADIO:
            "notify radio playing"
            self.controls.notify_title(text)

    def notify_error(self, msg):
        LOG.debug("Notify error, STOP state")
        self.set_state(STATE_STOP)
        self.controls.notify_error(msg)

    def play(self, bean):
        self.bean = bean
        if not bean:
            return None
        path = bean.path

        if not path:
            LOG.error("Can't play empty path!!!")
            return None

        
        self.state_stop()

        if self.prev_path != path:
            self.player = self.gstreamer_player()
            """equlizer settings"""
            if FC().is_eq_enable:
                pre = self.controls.eq.get_preamp()
                bands = self.controls.eq.get_bands()
                self.set_all_bands(pre, bands)
            
            if path.startswith("http://"):
                path = get_radio_source(path)
                LOG.debug("Try To play path", path)
                uri = path
                self.notify_title(uri)
            else:
                uri = 'file://' + urllib.pathname2url(path)
                if os.name == 'nt':
                    uri = 'file:' + urllib.pathname2url(path)

            LOG.info("Gstreamer try to play", uri)
            self.player.set_property("uri", uri)
            
            self.prev_path = path
        
        self.state_pause()
        time.sleep(0.2)        
        self.seek_seconds(bean.start_sec)
        self.state_play()
        self.volume(FC().volume)
        
        LOG.debug("current state before thread", self.get_state(), self.play_thread_id)
        self.play_thread_id = thread.start_new_thread(self.playing_thread, ())

    
    def set_all_bands(self, pre, values):
        if self.equalizer:
            for i, value in enumerate(values):      
                real = float(value) + pre
                if real >= 12:
                    real = 12
                if real <= -12:
                    real = -12
                self.equalizer.set_property("band%s" % i, real)
    
    def get_position_seek_ns(self):
        try:
            return self.player.query_position(gst.Format(gst.FORMAT_TIME), None)[0]
        except Exception, e:
            LOG.warn("GET query_position", e)
            return - 1
    
    def get_duration_seek_ns(self):
        try:
            return self.player.query_duration(gst.Format(gst.FORMAT_TIME), None)[0]
        except Exception, e:
            LOG.warn("GET query_duration", e)
            return - 1
    
    def playing_thread(self):
        thread_id = self.play_thread_id
        error_count = 0
        sec = 0
        
        LOG.debug("current state in thread", self.get_state())
         
        while thread_id == self.play_thread_id:
            try:
                time.sleep(0.2)
                duraction_int = self.get_duration_seek_ns()
                if duraction_int == -1:
                    time.sleep(1)
                    continue
                self.notify_init(duraction_int)
                break
            except Exception, e:
                LOG.info("Init playing thread", e)
                time.sleep(1)
                if error_count > 3:
                    LOG.warn("shit happens")
                    self.state_stop()
                    time.sleep(1)
                    self.state_play()
                error_count += 1

        time.sleep(0.2)

        if self.bean.duration_sec > 0:
            duraction_int = float(self.bean.duration_sec) * self.NANO_SECONDS
        
        LOG.debug("current state before while", self.get_state())
        
        self.set_state(STATE_PLAY)
        
        while thread_id == self.play_thread_id:
            try:
                position_int = self.get_position_seek_ns()
                if position_int > 0 and self.bean.start_sec > 0:
                    position_int = position_int - float(self.bean.start_sec) * self.NANO_SECONDS
                    LOG.debug(position_int, self.bean.start_sec, duraction_int)
                    if position_int + self.NANO_SECONDS > duraction_int:
                        self.notify_eos()
                
                if self.get_state() == STATE_PLAY:
                    sec += 1 
                    
                self.notify_playing(position_int, duraction_int, sec)
            except Exception, e:
                LOG.info("Playing thread error..." , e)

            time.sleep(1)

    def seek(self, percent, offset=0):
        seek_ns = self.duration_sec * (percent + offset) / 100 * self.NANO_SECONDS;

        if self.bean.start_sec > 0:
            seek_ns = seek_ns + float(self.bean.start_sec) * self.NANO_SECONDS

        self.player.seek_simple(gst.Format(gst.FORMAT_TIME), gst.SEEK_FLAG_FLUSH, seek_ns)
    
    def seek_seconds(self, seconds):
        if not seconds:
            return
        LOG.info("Start with seconds", seconds)
        seek_ns = (float(seconds) + 0.0) * self.NANO_SECONDS
        LOG.info("SEC SEEK SEC", seek_ns)
        self.player.seek_simple(gst.Format(gst.FORMAT_TIME), gst.SEEK_FLAG_FLUSH, seek_ns)
    
    def seek_ns(self, ns):
        if not ns:
            return        
        LOG.info("SEC ns", ns)
        self.player.seek_simple(gst.Format(gst.FORMAT_TIME), gst.SEEK_FLAG_FLUSH, ns)

    def volume(self, percent):
        value = percent / 100.0
        self.player.set_property('volume', value)
        #self.player.get_by_name("volume").set_property('volume', value + 0.0)

    def state_play(self):
        self.player.set_state(gst.STATE_PLAYING)
        self.current_state = STATE_PLAY
        #if FC().system_icons_dinamic:
        if self.bean.type == FTYPE_RADIO:
            self.controls.trayicon.on_dynamic_icons(FTYPE_RADIO)
        else:
            self.controls.trayicon.on_dynamic_icons(self.current_state)
    
    def get_current_percent(self):
        duration = self.get_duration_seek_ns()
        postion = self.get_position_seek_ns()
        return postion * 100.0 / duration 
    
    def seek_up(self, offset=3):                
        self.seek(self.get_current_percent(), offset)
        LOG.debug("SEEK UP")
    
    def seek_down(self, offset= -3):
        self.seek(self.get_current_percent(), offset)
        LOG.debug("SEEK DOWN")
    
    def restore_seek_ns(self):
        time.sleep(1)        
        self.player.seek_simple(gst.Format(gst.FORMAT_TIME), gst.SEEK_FLAG_FLUSH, self.remembered_seek_position)
        
    def state_stop(self, remeber_position=False):
        if remeber_position:
            self.player.set_state(gst.STATE_PAUSED)
            time.sleep(0.1)
            self.remembered_seek_position = self.get_position_seek_ns();
                        
        self.play_thread_id = None        
        self.player.set_state(gst.STATE_NULL)
        self.set_state(STATE_STOP)
        
        #if FC().system_icons_dinamic:
        self.controls.trayicon.on_dynamic_icons(self.current_state)
        LOG.debug("state STOP")

    def state_pause(self):
        self.player.set_state(gst.STATE_PAUSED)
        self.set_state(STATE_PAUSE)
        #if FC().system_icons_dinamic:
        self.controls.trayicon.on_dynamic_icons(self.current_state)
        
    def state_play_pause(self):
        if self.get_state() == STATE_PLAY:
            self.state_pause()
        else:
            self.state_play()
            

    def on_sync_message(self, bus, message):
        if message.structure is None:
            return
        self.controls.movie_window.draw_video(message)
        

    def on_message(self, bus, message):
        type = message.type

        if type == gst.MESSAGE_TAG  and message.parse_tag():
            if message.structure.has_field("title"):
                title = message.structure['title']
                self.notify_title(title)

        elif type == gst.MESSAGE_EOS:
            LOG.info("MESSAGE_EOS")
            self.notify_eos()
        elif type == gst.MESSAGE_ERROR:
            err, debug = message.parse_error()
            LOG.warn("Error: %s" % err, debug, err.domain, err.code)

            if err.code != 1:
                self.notify_error(str(err))

            
