from __future__ import unicode_literals

import logging
import os, sys, subprocess

import tornado.web

from mopidy import config, ext

from configobj import ConfigObj, ConfigObjError
from validate import Validator
import jinja2

__version__ = '0.1.4.1'

logger = logging.getLogger(__name__)

spec_file = os.path.join(os.path.dirname(__file__), 'settingsspec.ini')
template_file = os.path.join(os.path.dirname(__file__), 'index.html')
#config_file = '/etc/mopidy/mopidy.conf'

#log_file = '/var/log/mopidy/mopidy.log'

password_mask = '*'
reboot_required = ['network', 'musicbox']

def restart_program():
    """
    DOES NOT WORK WELL WITH MOPIDY 
    Hack from https://www.daniweb.com/software-development/python/code/260268/restart-your-python-program
    to support updating the settings, since mopidy is not able to do that yet
    Restarts the current program
    Note: this function does not return. Any cleanup action (like
    saving data) must be done before calling this function"""
    
    python = sys.executable
    os.execl(python, python, * sys.argv)

class Extension(ext.Extension):
    dist_name = 'Mopidy-WebSettings'
    ext_name = 'websettings'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema['musicbox'] = config.Boolean()
        schema['config_file'] = config.String()
        return schema

    def setup(self, registry):
        registry.add('http:app', {
            #'name': self.ext_name,
            'name': 'settings',
            'factory': websettings_app_factory,
        })

class WebSettingsRequestHandler(tornado.web.RequestHandler):

    def initialize(self, config):
        self.config_file = config['websettings']['config_file']

    def get(self):
        templateLoader = jinja2.FileSystemLoader( searchpath = "/" )
        templateEnv = jinja2.Environment( loader=templateLoader )
        template = templateEnv.get_template(template_file)
        error = ''
        #read config file
        try:
            iniconfig = ConfigObj(self.config_file, configspec=spec_file, file_error=True, encoding='utf8')
        except (ConfigObjError, IOError), e:
            error = 'Could not load ini file! %s %s %s' % (e, ConfigObjError, IOError)
        #read values of valid items (in the spec-file)
        validItems = ConfigObj(spec_file, encoding='utf8')
        templateVars = {
            "error": error
        }
        #iterate over the valid items to get them into the template
        for item in validItems:
            for subitem in validItems[item]:
                itemName = item + '__' + subitem
                try:
                    configValue = iniconfig[item][subitem]
                    #compare last 8 caracters of subitemname
                    if subitem[-8:] == 'password' and configValue != '':
                        configValue = password_mask * len(iniconfig[item][subitem])
                    templateVars[itemName] = configValue
                except:
                    pass

        self.write(template.render ( templateVars ) )

class WebPostRequestHandler(tornado.web.RequestHandler):

    def initialize(self, config):
        self.config_file = config.get('websettings')['config_file']

    def post(self):
        apply_html = ''
        apply_string = 'restart Mopidy'
        error = ''
        try:
            iniconfig = ConfigObj(self.config_file, configspec=spec_file, file_error=True, encoding='utf8')
        except (ConfigObjError, IOError), e:
            error = 'Could not load ini file!'
        if error == '':
            validItems = ConfigObj(spec_file, encoding='utf8')
            templateVars = {
                "error": error
            }
            #iterate over the items, so that only valid items are processed
            for item in validItems:
                for subitem in validItems[ item ]:
                    itemName = item + '__' + subitem
                    argumentItem = self.get_argument(itemName, default='')
                    if argumentItem:
                        #don't edit config value if password mask
                        if subitem[-8:] == 'password':
                          if argumentItem == (password_mask * len(argumentItem)) or argumentItem == '':
                              continue
                        #create section entry if it doesn't exist
                        try:
                            # Check if changing this setting requires a system reboot.
                            if iniconfig[item][subitem] != argumentItem and item in reboot_required:
                                apply_string = 'reboot system'
                            iniconfig[item][subitem] = argumentItem
                        except:
                            iniconfig[item] = {}
                            iniconfig[item][subitem] = argumentItem
            if iniconfig['audio']['mixer'] == 'alsamixer':
                iniconfig['alsamixer']['enabled'] = 'true'
            else:
                iniconfig['alsamixer']['enabled'] = 'false'

            iniconfig.write()
            error = 'Settings Saved!'
            apply_html = '<form action="apply" method="post"><input type="submit" name="method" value="Apply changes now (' + apply_string + ')" />'

        message = '<html><body><h1>' + error + '</h1><p>' + apply_html + '<br/><br/><a href="/">Home</a><br/></p></body></html>'
        self.write(message)

class WebApplyRequestHandler(tornado.web.RequestHandler):

    def initialize(self): pass

    def post(self):
        method = self.get_argument('method', None)
        if method != None:
            if 'reboot' in method:
                status='Rebooting Musicbox system...'
                os.system("sudo shutdown -r now")
            elif 'restart' in method:
                status='Restarting Mopidy service...'
                os.system("sudo /etc/init.d/mopidy restart")
            else:
                status='Error while applying ' + method
        logger.info(status)
        message = '<html><body><h1>' + status + '</h1><br/><br/><a href="/">Home</a><br/></p></body></html>'
        self.write(message)

class WebRebootRequestHandler(tornado.web.RequestHandler):

    def initialize(self): pass

    def post(self):
        logger.info('Halting system')
        os.system("sudo shutdown -r now")
        os.system("shutdown -r now")

class WebShutdownRequestHandler(tornado.web.RequestHandler):

    def initialize(self): pass

    def post(self):
        logger.info('Halting system')
        os.system("sudo shutdown -h now")
        os.system("shutdown -h now")


def websettings_app_factory(config, core):
    return [
        ('/',        WebSettingsRequestHandler, {'config': config}),
        ('/save',    WebPostRequestHandler,     {'config': config}),
        ('/apply',   WebApplyRequestHandler,                      ),
        ('/reboot',  WebRebootRequestHandler,                     ),
        ('/shutdown', WebShutdownRequestHandler,                  )
    ]
