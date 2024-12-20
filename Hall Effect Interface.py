import numpy   as _n
import time    as _time
import spinmob as _s
import spinmob.egg as _egg
_g = _egg.gui
import mcphysics as _mp


_debug_enabled = True
_debug = _mp._debug
_p = _mp._p

# Serial COM markers
endMarker   = '\n'
terminator  = '\r\n'


class keithley_dmm_api():
    """
    This object lets you query the Keithley 199 or 2700 for voltages on any of its
    channels. It is based on old code from those before us.

    FAQ: Use shift + scan setup on the front panel to choose a channel, and
    shift + trig setup to set the trigger mode to "continuous". Finally,
    make sure the range is appropriate, such that the voltage does not overload.
    Basically, if you see a fluctuating number on the front panel, it's
    all set to take data via self.get_voltage() (see below).

    Parameters
    ----------
    name='ASRL3::INSTR'
        Visa resource name. Use R&S Tester 64-bit or NI-MAX to find this.

    pyvisa_py=False
        If True, use the all-python VISA implementation. On Windows, the simplest
        Visa implementation seems to be Rhode & Schwarz (streamlined) or NI-VISA (bloaty),
        with pyvisa_py=False.

    NOTE
    ----
    At some point we should inherit the common functionality of these visa
    objects with those found in visa_tools.py. All new instruments should be
    written this way, for sure! This instrument might be too low-level though...
    """



    def __init__(self, name='ASRL4::INSTR', pyvisa_py=False):
        if not _mp._visa: _s._warn('You need to install pyvisa to use the Keithley DMMs.')

        # Create a resource management object
        if _mp._visa:
            if pyvisa_py: self.resource_manager = _mp._visa.ResourceManager('@py')
            else:         self.resource_manager = _mp._visa.ResourceManager()
        else: self.resource_manager = None

        # Get time t=t0
        self._t0 = _time.time()

        # Try to open the instrument.
        try:
            self.instrument = self.resource_manager.open_resource(name)

            # Test that it's responding and figure out the type.
            try:
                # Clear out the buffer, in case the instrument was
                # Just turned on.
                self.read()

                # Ask for the model identifier
                s = self.machine_status()

                # DMM model 199
                if s[0:3] in ['100', '199']: self.model = 'KEITHLEY199'
                else:
                    print("ERROR: Currently we only handle Keithley 199 DMMs")
                    self.instrument.close()
                    self.instrument = None

            except:
                print("ERROR: Instrument did not reply to ID query. Entering simulation mode.")
                self.instrument.close()
                self.instrument = None

        except:
            self.instrument = None
            if self.resource_manager:
                print("ERROR: Could not open instrument. Entering simulation mode.")
                print("Available Instruments:")
                for name in self.resource_manager.list_resources(): print("  "+name)

    def write(self, message, process_events=False):
        """
        Writes the supplied message.

        Parameters
        ----------
        message
            String message to send to the DMM.

        process_events=False
            Optional function to be called in between communications, e.g., to
            update a gui.
        """
        _debug('write('+"'"+message+"'"+')')

        if self.instrument == None: s = None
        else:                       s = self.instrument.write(message)

        if process_events: process_events()
        return s

    def read(self, process_events=False):
        """
        Reads a message and returns it.

        Parameters
        ----------
        process_events=False
            Optional function to be called in between communications, e.g., to
            update a gui.
        """
        _debug('read()')
        self.write('++read 10')

        if process_events: process_events()

        if self.instrument == None: response = ''
        else:                       response = self.instrument.read()

        if process_events: process_events()

        _debug('  '+repr(response))
        return response.strip()

    def query(self, message='U0X', process_events=False):
        """
        Writes the supplied message and reads the response.
        """
        _debug("query('"+message+"')")

        self.write(message, process_events)
        return self.read(process_events)

    def reset(self):
        """
        We should look up the command that is actually sent.
        """
        if self._device_name == "KEITHLEY199":
            self.write("L0XT3G5S1X")
        elif self._device_name == "KEITHLEY2700":
            self.write("INIT:CONT OFF")
            self.write("CONF:VOLT:DC")

    def unlock(self):
        """
        Tells the Keithley to listen to the front panel buttons and ignore instructions from the computer.
        """
        self.write("++loc")
        
    def machine_status(self):
        """
        Get the machine status string.
        This can be decoded to get the full state of the Keithley 199.
        """
        return self.query("U0X").strip("\r\n")
        
    def lock(self):
        """
        Tells the Keithley to ignore the front panel buttons and listen to instructions from the computer.
        """
        self.write("++llo")

    def get_voltage(self, channel=1, process_events=False):
        """
        Returns the time just after reading the voltage and voltage value
        for the supplied channel.

        Parameters
        ----------
        channel=0:
            Channel number to read (integer).
        process_events=False:
            Optional function that will run whenever possible
            (e.g., to update a gui).
        """
        # Simulation mode
        if self.instrument == None:
            _time.sleep(0.4)
            return _time.time() - self._t0, _n.random.rand()

        # Real deal
        elif self.model == 'KEITHLEY199':

            # Select the channel
            self.write("F0R0N%dX" % channel, process_events)

            # Ask for the voltage & get rid of the garbage
            try:
                s = self.read(process_events)
            except:
                print("ERROR: Timeout on channel "+str(channel))
                return _time.time() - self._t0, _n.nan

            # Return the voltage
            try:
                return _time.time() - self._t0, float(s[4:].strip())
            except:
                print("ERROR: Bad format "+repr(s))
                return _time.time() - self._t0, _n.nan


    def close(self):
        """
        Closes the connection to the device.
        """
        _debug("close()")
        if not self.instrument == None: self.instrument.close()


class Thermocouple_api():
    """
    Commands-only object for interacting with the arduino based
    Atomic Spectra Monochromator hardware.
    
    Parameters
    ----------
    port='COM5' : str
        Name of the port to connect to.
        
    baudrate=115200 : int
        Baud rate of the connection. Must match the instrument setting.
        
    timeout = 1 : int
        How long to wait for responses before giving up (s). 
        
    """
    def __init__(self, port='COM5', baudrate=115200, timeout=.5):
                
        if not _mp._serial:
            print('You need to install pyserial to use the Atomic Spectra Monochromator.')
            self.simulation_mode = True
        
        self.simulation_mode = False
        
        # If the port is "Simulation"
        if port=='Simulation': self.simulation_mode = True
        
        # If we have all the libraries, try connecting.
        if not self.simulation_mode:
            try:
                # Create the instrument and ensure the settings are correct.
                self.serial = _mp._serial.Serial(port = port, baudrate = baudrate, timeout = timeout)
                
            # Something went wrong. Go into simulation mode.
            except Exception as e:
                  print('Could not open connection to "'+port+':'+'" at baudrate '+str(baudrate)+'. Entering simulation mode.')
                  print(e)
                  self.simulation_mode = True
                  self.serial = None
                  return
                
        # Container for scan data as it is dynamically acquired          
        self.scan_data = ''
                
        # Give the arduino time to run the setup loop
        _time.sleep(2)
        
        if (self.getID()[:10] != 'Ugrad Labs') : self.serial = None
    

    def getID(self):
        """
        Get the version of sketch currently on the arduino board.

        Returns
        -------
        str
            A string describing the arduino sketch version and compilation date.

        """
        self.write('*IDN?')
        
        return self.read()
    
    def getTemperature(self):
        """
        Get the current thermocouple temperature.

        Returns
        -------
        temp: float
            Thermocouple temperature.

        """
        self.write("THERMO:TEMP?")
        
        s = self.read()
        
        try:     temp = float(s)
        except:  temp = s
        
        return temp  
    
    def setOneshot(self):
        """
        """
        
        self.write("ONESHOT")
        
    def getConversionStatus(self):
        """
        """
        self.write('THERMO:STATUS?')
        
        return self.read()        
        
    def getThermocoupleType(self):
        """
        """
        
        self.write('THERMO:TYPE?')

        return self.read()
    
    def setThermocoupleType(self, thermocoupleType):
        """
        """
        self.write('THERMO:TYPE '+thermocoupleType)
    
    def getMode(self):
        
        self.write("THERMO:MODE?")
        
        return self.read()
    
    def setMode(self, mode):
        """            
        """
        self.write("THERMO:MODE "+mode)
     
    def getCJTemperature(self):
        
        self.write("COLDJ:TEMP? ")
        
        return self.read()
    
    
    ## Serial COM ##
    
    def write(self,raw_data):
        """
        Writes data to the serial line, formatted appropriately to be read by the monochromator.        
        
        Parameters
        ----------
        raw_data : str
            Raw data string to be sent to the arduino.
        
        Returns
        -------
        None.
        
        """
        encoded_data = (raw_data + endMarker).encode()
        self.serial.write(encoded_data) 
    
    def read(self):
        """
        Reads data from the serial line.
        
        Returns
        -------
        str
            Raw data string read from the serial line.
        """
        try:
            s = self.serial.read_until(expected = terminator.encode()).decode()
        except:
            print("ERROR: Timeout")
            return _n.nan
        
        try:
            return s.strip(terminator)
        except:
            print("ERROR: Bad format "+repr(s))
            return _n.nan
            
            
    def disconnect(self):
        """
        Disconnects the port.
        """
        if not self.simulation_mode and self.serial != None: 
            self.serial.close()
            self.serial = None
            
            
class Hall_interface(_g.BaseObject):
    """
    Graphical front-end for the Keithley 199 DMM.

    Parameters
    ----------
    autosettings_path='keithley_dmm'
        Which file to use for saving the gui stuff. This will also be the first
        part of the filename for the other settings files.

    pyvisa_py=False
        Whether to use pyvisa_py or not.

    block=False
        Whether to block the command line while showing the window.
    """
    def __init__(self, autosettings_path='Hall_interface', pyvisa_py=False, block=False):
        if not _mp._visa: _s._warn('You need to install pyvisa to use the Keithley DMMs.')

        # No devices selected yet
        self.keithley_api = None
        self.arduino_api = None

        # Internal parameters
        self._pyvisa_py = pyvisa_py

        # Pattern the GUI
        self.window    = _g.Window('Hall Interface', autosettings_path=autosettings_path+'_window')
        self.window.event_close = self.event_close
        self.grid_top  = self.window.place_object(_g.GridLayout(False))
        self.window.new_autorow()
        self.grid_bot  = self.window.place_object(_g.GridLayout(False), alignment=0)
        
        # Button for connection to the Keithley
        self.button_keithley_connect   = self.grid_top.place_object(_g.Button('Connect', True, False))

        # Button list for selecting Keithley channels
        self.buttons = []
        for n in range(8):
            self.buttons.append(self.grid_top.place_object(_g.Button(str(n+1),True, True).set_width(25), column=n+1))
            self.buttons[n].signal_toggled.connect(self.save_gui_settings)
            
        # Label DMM name/connection status
        self.label_dmm_name = self.grid_top.place_object(_g.Label('Disconnected'), column=9)
        
        self.grid_top.new_autorow()
        
        # Arduino connection button 
        self.button_arduino_connect   = self.grid_top.place_object(_g.Button('Connect', True, False))            
        
        # Buttons for selecting Arduino functions
        self.buttonT = self.grid_top.place_object(_g.Button('T',True, False).set_width(25))
        self.buttonT.signal_toggled.connect(self.save_gui_settings)
        
        # Label for Arduino connection status
        self.label_arduino = self.grid_top.place_object(_g.Label('Disconnected'), column=9)
        
        self.grid_top.new_autorow()
        
        # Button for enabling acquistion on selected dmm channels/Arduino functions
        self.button_acquire = self.grid_top.place_object(_g.Button('Acquire',True).disable(), column=10, alignment=1)
        
        # Settings window (will display relevant DMM/Arduino information)
        self.settings  = self.grid_bot.place_object(_g.TreeDictionary()).set_width(250)
        
        # Create data tabs
        self.tabs_data = self.grid_bot.place_object(_g.TabArea(autosettings_path+'_tabs_data.txt'), alignment=0)
        self.tab_raw   = self.tabs_data.add_tab('Raw Data')
        self.tab_temp  = self.tabs_data.add_tab('Temperature')
        
        # Main raw data plotting 
        self.label_path = self.tab_raw.add(_g.Label('Output Path:').set_colors('cyan' if _s.settings['dark_theme_qt'] else 'blue'))
        self.tab_raw.new_autorow()
        self.plot_raw   = self.tab_raw.place_object(_g.DataboxPlot('*.csv', autosettings_path+'_plot_raw.txt' , autoscript=2), alignment=0)
        
        # Extra lone emperature plotting
        self.label_path = self.tab_temp.add(_g.Label('Output Path:').set_colors('cyan' if _s.settings['dark_theme_qt'] else 'blue'))
        self.tab_temp.new_autorow()
        self.plot_temp  = self.tab_temp.place_object(_g.DataboxPlot('*.csv', autosettings_path+'_plot_temp.txt', autoscript=2), alignment=0)


        # Create a resource management object to populate the list
        if _mp._visa:
            if pyvisa_py: self.resource_manager = _mp._visa.ResourceManager('@py')
            else:         self.resource_manager = _mp._visa.ResourceManager()
        else: self.resource_manager = None

        # Populate the list.
        names = []
        if self.resource_manager:
            for x in self.resource_manager.list_resources():
                if self.resource_manager.resource_info(x).alias:
                    names.append(str(self.resource_manager.resource_info(x).alias))
                else:
                    names.append(x)
        
        # Grab availible comports
        comports = _mp._serial.tools.list_ports.comports()
        ports    = []
        d_index  = 0
                    
        for i, comport in enumerate(sorted(comports)):
            port,desc,hwid = comport
            ports.append("{}: {}".format(port, desc))
            
            # Check for Arduino label in the port name
            if 'Arduino' in desc: d_index = i
        

        # Keithley settings
        self.settings.add_parameter('Keithley/Device', default_list_index=3,type='list', values=['Simulation']+names)
        self.settings.add_parameter('Keithley/ID' , value='-', readonly = True)
        self.settings.add_parameter('Keithley/Status' , value = 'Not Connected', readonly = True)
        self.settings.add_parameter('Keithley/Configuration', value = ' ',readonly=True)
        self.settings.add_parameter('Keithley/Configuration/Multiplex', value = ' ',readonly=True)
        self.settings.add_parameter('Keithley/Configuration/Function', value = ' ',readonly=True)
        self.settings.add_parameter('Keithley/Configuration/Range', value = ' ',readonly=True)
        self.settings.add_parameter('Keithley/Configuration/Rate', value = ' ',readonly=True)
        self.settings.add_parameter('Keithley/Unlock', True, tip='Unlock the device\'s front panel after acquisition.')
        self.settings.add_parameter('Keithley/  ', value = ' ',readonly=True)
        self.settings.add_parameter('Keithley/Channel', value = ' ',readonly=True)
        for i in range(8):
            self.settings.add_parameter('Keithley/Channel/%d'%(i+1), value = 0.000,suffix = 'V',siPrefix = True,readonly=True)
            
        self.settings.add_parameter('Keithley/ ', value = ' ',readonly=True)

        
        # Arduino settings
        self.settings.add_parameter('Arduino/Port', default_list_index=d_index+1, type='list', values=['Simulation']+ports)
        self.settings.add_parameter('Arduino/Firmware' , value='-', readonly = True)
        self.settings.add_parameter('Arduino/Status' , value = 'Not Connected', readonly = True)
        self.settings.add_parameter('Arduino/', value = ' ',readonly=True)
        self.settings.add_parameter('Arduino/Thermocouple/Type', value=' -', readonly = True)
        self.settings.add_parameter('Arduino/Thermocouple/Conversion Mode', value=' -', readonly = True)
        self.settings.add_parameter('Arduino/Thermocouple/Temperature', value=0.0, suffix = '°C', readonly = True)

        # Connect all the signals
        self.button_keithley_connect.signal_clicked.connect(self._button_keithley_connect_clicked)
        self.button_arduino_connect.signal_clicked .connect(self._button_arduino_connect_clicked)
        self.button_acquire.signal_clicked.connect(self._button_acquire_clicked)

        # Run the base object stuff and autoload settings
        _g.BaseObject.__init__(self, autosettings_path=autosettings_path)
        self._autosettings_controls = ['self.buttons[0]', 'self.buttons[1]',
                                       'self.buttons[2]', 'self.buttons[3]',
                                       'self.buttons[4]', 'self.buttons[5]',
                                       'self.buttons[6]', 'self.buttons[7]']
        self.load_gui_settings()

        # Show the window.
        self.window.show(block)

    def _button_keithley_connect_clicked(self, *a):
        """
        Connects or disconnects the VISA resource.
        """

        # If we're supposed to connect
        if self.button_keithley_connect.get_value():
            
            # Close it if it exists for some reason
            if not self.keithley_api == None: self.keithley_api.close()
            
            # Make the new one
            self.keithley_api = keithley_dmm_api(self.settings['Keithley/Device'], self._pyvisa_py)
            
            self.label_dmm_name.set_text('Simulation Mode')

            # Tell the user what dmm is connected
            if self.keithley_api.instrument == None:
                self.label_dmm_name.set_colors('pink' if _s.settings['dark_theme_qt'] else 'red')
                self.button_keithley_connect.set_colors(background='pink')
                self.settings['Keithley/Status'] = 'Simulation Mode'
            else:
                self.label_dmm_name.set_text(self.keithley_api.model + ' Connected')
                self.label_dmm_name.set_style('')
                self.label_dmm_name.set_colors(text='blue')
                
                self.keithley_api.write('F0R0N1X')
                
            # Enable the Acquire button
            self.button_acquire.enable()

        else:

            # Close down the instrument
            if not self.keithley_api.instrument == None:
                self.keithley_api.close()
            
            self.keithley_api = None

            # Make sure it's not still red.
            self.label_dmm_name.set_style('')
            self.button_keithley_connect.set_colors(background='')
            
            # Disable the acquire button
            self.button_acquire.disable()

        #    
        self.update_keithley_settings()

    def _button_arduino_connect_clicked(self):
        
        # Check if the connect button is being enabled
        if self.button_arduino_connect.get_value():
            
            # Close it if it exists for some reason
            if not self.arduino_api  == None: self.arduino_api.disconnect()
            
            # Make the new one
            self.arduino_api  = Thermocouple_api(self.settings['Arduino/Port'][:4])

            if self.arduino_api.serial == None:
                    self.settings['Arduino/Status'] = 'Simulation Mode'
                    self.button_keithley_connect.set_colors(background='pink')
            else:
                self.label_arduino.set_text('Arduino Connected')
                self.label_arduino.set_style('')
                self.label_arduino.set_colors(text='blue')
                
                # Enable the Acquire button
                self.button_acquire.enable()
        
        else:
            
            if not self.arduino_api.serial == None:
                self.arduino_api.disconnect()
            
            self.arduino_api = None
            
            self.label_arduino.set_text('Disconnected')
            self.label_arduino.set_colors(text='')

            # Disable the acquire button
            self.button_acquire.disable()            
            
        self.update_arduino_settings()

    def _button_acquire_clicked(self, *a):
        """
        Get the enabled curves, storing them in plot_raw.
        """
        _debug('_button_acquire_clicked()')

        # Don't double-loop!
        if not self.button_acquire.is_checked(): return

        # Don't proceed if we have no connection
        if self.keithley_api == None and self.arduino_api==None:
            self.button_acquire(False)
            return

        # Ask the user for the dump file
        self.path = _s.dialogs.save('*.csv', 'Select an output file.', force_extension='*.csv')
        if self.path == None:
            self.button_acquire(False)
            return

        # Update the label
        self.label_path.set_text('Output Path: ' + self.path)

        _debug('  path='+repr(self.path))

        # Disable the connection button
        self._set_acquisition_mode(True)
        
        # Clear the channel voltages and Thermocouple temperature values
        for n in range(8):
            self.settings['Keithley/Channel/%d'%(n+1)] = 0.0
        self.settings['Arduino/Thermocouple/Temperature'] = 0.0

        # For easy coding
        d = self.plot_raw
        e = self.plot_temp

        # Set up the databox columns
        _debug('  setting up databox')
        d.clear()
        e.clear()
        
        for n in range(len(self.buttons)):
            if self.buttons[n].is_checked():
                d['t'+str(n+1)] = []
                d['v'+str(n+1)] = []
        
        if self.buttonT.is_checked():
            d['t9'] = []
            d['T']  = []
            
            e['t']  = []
            e['T']  = []


        # Reset the clock and record it as header
        self._t0 =  _time.time()
        try:
            self.keithley_api._t0 = self._t0
            self._dump(['Date:', _time.ctime()], 'w')
            self._dump(['Time:', self.keithley_api._t0])
        except:
            self._dump(['Date:', _time.ctime()], 'w')
            self._dump(['Time:', self._t0])

        # And the column labels!
        self._dump(self.plot_raw.ckeys)

        # Loop until the user quits
        _debug('  starting the loop')
        while self.button_acquire.is_checked():

            # Next line of data
            data = []

            # Get all the voltages we're supposed to
            for n in range(len(self.buttons)):

                # If the button is enabled, get the time and voltage
                if self.buttons[n].is_checked():

                    _debug('    getting the voltage')

                    # Get the time and voltage, updating the window in between commands
                    t, v = self.keithley_api.get_voltage(n+1, self.window.process_events)
                    
                    self.settings['Keithley/Channel/%d'%(n+1)] = v


                    # Append the new data points
                    d['t'+str(n+1)] = _n.append(d['t'+str(n+1)], t)
                    d['v'+str(n+1)] = _n.append(d['v'+str(n+1)], v)

                    # Update the plot
                    self.plot_raw.plot()
                    self.window.process_events()

                    # Append this to the list
                    data = data + [t,v]
            
            if self.buttonT.is_checked():        
                t, T = _time.time()-self.keithley_api._t0, self.arduino_api.getTemperature()    
                
                self.settings['Arduino/Thermocouple/Temperature'] = T
                        
                d['t9'] = _n.append(d['t9'],t)
                d['T']  = _n.append(d['T'] ,T)
                
                e['t']  = _n.append(e['t'],t)
                e['T']  = _n.append(e['T'] ,T)
                
                data = data + [t,T]
            
            self.plot_raw .plot()
            self.plot_temp.plot() 
            self.window.process_events()

            # Write the line to the dump file
            self._dump(data)

        _debug('  Loop complete!')

        # Unlock the front panel if we're supposed to
        if self.settings['Keithley/Unlock']: self.keithley_api.unlock()

        # Re-enable the connect button
        self._set_acquisition_mode(False)

    def _dump(self, a, mode='a'):
        """
        Opens self.path, writes the list a, closes self.path. mode is the file
        open mode.
        """
        _debug('_dump('+str(a)+', '+ repr(mode)+')')

        # Make sure everything is a string
        for n in range(len(a)): a[n] = str(a[n])
        self.a = a
        
        # Write it.
        f = open(self.path, mode)
        f.write(','.join(a)+'\n')
        f.close()
        
    def update_keithley_settings(self):
        
        if(self.keithley_api == None):
            
            self.label_dmm_name.set_text('Disconnected')
            self.settings['Keithley/ID']     = ' -'
            self.settings['Keithley/Status'] = 'Not Connected'
            
            self.settings['Keithley/Configuration/Multiplex'] = ''
            self.settings['Keithley/Configuration/Function']  = ''
            self.settings['Keithley/Configuration/Range']     = ''
            self.settings['Keithley/Configuration/Rate']      = ''
            return
        
        
        mstatus = self.keithley_api.machine_status()

        ID = mstatus[:3]      # DMM ID
        M  = mstatus[3]       # DMM Multiplex
        F  = int(mstatus[5])  # DMM Function
        R  = int(mstatus[21]) # DMM Range
        S  = int(mstatus[22]) # DMM Rate
        
        self.settings['Keithley/Status'] = 'Connected'
        self.settings['Keithley/ID']     = ID
        
        if(M): self.settings['Keithley/Configuration/Multiplex'] = 'ENABLED'
        else:  self.settings['Keithley/Configuration/Multiplex'] = 'DISABLED'
       
        if  (F == 0): self.settings['Keithley/Configuration/Function'] = 'DC VOLTS'
        elif(F == 1): self.settings['Keithley/Configuration/Function'] = 'AC VOLTS'
        elif(F == 2): self.settings['Keithley/Configuration/Function'] = 'OHMS'
        elif(F == 3): self.settings['Keithley/Configuration/Function'] = 'DC CURRENT'
        elif(F == 4): self.settings['Keithley/Configuration/Function'] = 'AC CURRENT'
        elif(F == 5): self.settings['Keithley/Configuration/Function'] = 'ACV dB'
        elif(F == 6): self.settings['Keithley/Configuration/Function'] = 'ACA dB'
        
        if(F == 0):
            if  (R == 0): self.settings['Keithley/Configuration/Range'] = 'AUTO'
            elif(R == 1): self.settings['Keithley/Configuration/Range'] = '300 mV'
            elif(R == 2): self.settings['Keithley/Configuration/Range'] = '3 V'
            elif(R == 3): self.settings['Keithley/Configuration/Range'] = '30 V'
            elif(R == 4): self.settings['Keithley/Configuration/Range'] = '300V'
            elif(R == 5): self.settings['Keithley/Configuration/Range'] = '300V'
            elif(R == 6): self.settings['Keithley/Configuration/Range'] = '300V'
            elif(R == 7): self.settings['Keithley/Configuration/Range'] = '300V'
        else:
            self.settings['Keithley/Configuration/Range'] = '-'
        
        if (S == 0): self.settings['Keithley/Configuration/Rate'] = '4 1/2 Digits'
        if (S == 1): self.settings['Keithley/Configuration/Rate'] = '5 1/2 Digits'    
    
    def update_arduino_settings(self):
        
        if(self.arduino_api == None):
            self.settings['Arduino/Firmware']                     = ' -'
            self.settings['Arduino/Thermocouple/Type']            = ' -'
            self.settings['Arduino/Thermocouple/Conversion Mode'] = ' -'
            self.settings['Arduino/Status']                       = 'Not Connected'
            return
        
        self.settings['Arduino/Firmware']                     = self.arduino_api.getID().split(',')[2]
        self.settings['Arduino/Thermocouple/Type']            = self.arduino_api.getThermocoupleType()
        self.settings['Arduino/Thermocouple/Conversion Mode'] = self.arduino_api.getMode()
        self.settings['Arduino/Status']                       = 'Connected'
    
    def _set_acquisition_mode(self, mode=True):
        """
        Enables / disables the appropriate buttons, depending on the mode.
        """
        _debug('_set_acquisition_mode('+repr(mode)+')')
        
        self.button_keithley_connect.disable(mode)
        for b in self.buttons: b.disable(mode)
        
        self.button_arduino_connect.disable(mode)
        self.buttonT.disable(mode)

    def event_close(self, *a):
        """
        Quits acquisition loop when the window closes.
        """
        self.button_acquire.set_checked(False)


if __name__ == '__main__':
    self = Hall_interface()
