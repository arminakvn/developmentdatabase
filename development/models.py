from django.contrib.gis.db import models
from django.utils.translation import ugettext as _
from django.contrib.auth.models import User

from django.conf import settings
from django.utils.dateparse import parse_datetime

import pytz
import requests
import reversion

# south introspection rules
try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([], ['^django\.contrib\.gis\.db\.models\.fields\.PointField'])
    add_introspection_rules([], ['^django\.contrib\.gis\.db\.models\.fields\.MultiPolygonField'])
except ImportError:
    pass

class CommunityType(models.Model):
    name = models.CharField(max_length=50)

    def __unicode__(self):
        return self.name


class Subregion(models.Model):
    name = models.CharField(max_length=50)
    abbr = models.CharField(max_length=50)

    class Meta:
        verbose_name = _('Subregion')
        verbose_name_plural = _('Subregions')
        ordering = ['abbr']

    def __unicode__(self):
        return self.abbr
    

class Municipality(models.Model):
    muni_id = models.IntegerField('Municipality ID', primary_key=True)
    name = models.CharField('Municipality Name', max_length=50, unique=True)
    communitytype = models.ForeignKey(CommunityType, blank=True, null=True)
    subregion = models.ForeignKey(Subregion, null=True)
    
    geometry = models.MultiPolygonField(srid=26986)
    objects = models.GeoManager()
    
    class Meta:
        verbose_name_plural = 'Municipalities'
        ordering = ['name']
    
    def __unicode__(self):
        return self.name


class Taz(models.Model):
    """ 
    Transportation Analysis Zone, 
    smaller regional units than towns. 
    """
    
    taz_id = models.IntegerField(primary_key=True)
    municipality = models.ForeignKey(Municipality)
    
    geometry = models.MultiPolygonField(srid=26986)
    objects = models.GeoManager()
    
    class Meta:
        verbose_name=u'TAZ'
        verbose_name_plural = 'TAZs'
        ordering = ['taz_id']
    
    def __unicode__(self):
        return "%s - %s" % (self.taz_id, self.municipality)


class ZipCode(models.Model):
    """
    Massachusetts Zip Codes, used for approx. geocoding
    """

    zipcode = models.CharField(max_length=5)
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=2)

    geometry = models.MultiPolygonField(srid=26986)
    objects = models.GeoManager()

    class Meta:
        verbose_name = _('ZipCode')
        verbose_name_plural = _('ZipCodes')
        ordering = ['zipcode']

    def __unicode__(self):
        return self.zipcode

    @property
    def address(self):
        """ Returns formatting to fit in street addresses """
        return '%s, %s %s' % (self.name, self.state, self.zipcode)
    


class ProjectStatus(models.Model):
    name = models.CharField(max_length=20)

    class Meta:
        verbose_name_plural = 'Project statuses'

    def __unicode__(self):
        return self.name
    
class ZoningTool(models.Model):
    name = models.CharField('Zoning Tool', max_length=3)

    def __unicode__(self):
        return self.name


class ProjectType(models.Model):
    name = models.CharField('Project Type', max_length=100)
    order = models.IntegerField(default=0)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['order']


class WalkScore(models.Model):
    """ Model class according to http://www.walkscore.com/professional/api.php """

    status = models.IntegerField()
    walkscore = models.IntegerField()
    description = models.CharField(max_length=100)
    updated = models.DateTimeField()
    ws_link = models.URLField()
    snapped_lat = models.FloatField()
    snapped_lon = models.FloatField()

    geometry = models.PointField(geography=True, null=True)
    objects = models.GeoManager() 

    class Meta:
        verbose_name = _('WalkScore')
        verbose_name_plural = _('WalkScores')

    def __unicode__(self):
        return '%i (%s)' % (self.walkscore, self.description)

    def save(self, *args, **kwargs):
        try:
            self.geometry = Point(self.snapped_lon, self.snapped_lat)
        except:
            self.geometry = None        
        super(WalkScore, self).save(*args, **kwargs)
    

class TODStation(models.Model):
    """ Adjusted buffer around transit stations """

    station_id = models.IntegerField()
    station_name = models.CharField(max_length=50)
    subway = models.BooleanField()
    comrail = models.BooleanField()
    taz = models.ForeignKey(Taz)

    geometry = models.MultiPolygonField(srid=26986)
    objects = models.GeoManager()

    class Meta:
        verbose_name = _('TODStation')
        verbose_name_plural = _('TODStations')

    def __unicode__(self):
        return self.station_name
    

class Project(models.Model):
    """
    An economic or housing development project.
    """

    dd_id = models.AutoField(primary_key=True)
    taz = models.ForeignKey(Taz, blank=True, null=True, editable=False)
    ddname = models.CharField('Project Name', max_length=100)
    status = models.ForeignKey(ProjectStatus)
    complyr = models.IntegerField('Year of Completion', null=True, help_text='Estimated or actual.')
    prjacrs = models.FloatField('Project Area', null=True, help_text='In acres.')
    rdv = models.NullBooleanField('Redevelopment', blank=True, null=True)
    
    singfamhu = models.IntegerField('Single Family Housing', blank=True, null=True, help_text='Number of units.')
    twnhsmmult = models.IntegerField('Townhouse and Small Multifamily', blank=True, null=True, help_text='Number of units.')
    lgmultifam = models.IntegerField('Large Multifamily', blank=True, null=True, help_text='Number of units.')
    tothu = models.FloatField('Total Housing', null=True, help_text='Number of units.')
    gqpop = models.IntegerField('Group Quarters', blank=True, null=True, help_text='Number of beds.')
    pctaffall = models.FloatField('Affordable Units', blank=True, null=True, help_text='In percent.')
    clustosrd = models.NullBooleanField('Cluster Subdivision', blank=True, null=True)
    ovr55 = models.NullBooleanField('Age Restricted', blank=True, null=True)
    mxduse = models.NullBooleanField('Mixed Use', blank=True, null=True)
    ch40 = models.ForeignKey(ZoningTool, blank=True, null=True)

    rptdemp = models.FloatField('Reported Employment', blank=True, null=True)
    emploss = models.FloatField('Employment Loss', blank=True, null=True)
    totemp = models.FloatField('Est. employment', blank=True, null=True)
    commsf = models.FloatField('Total Non-Residential Development', null=True, help_text='In square feet.')
    retpct = models.FloatField('Retail / Restaurant Percentage', blank=True, null=True, help_text='In percent.')
    ofcmdpct = models.FloatField('Office / Medical Percentage', blank=True, null=True, help_text='In percent.')
    indmfpct = models.FloatField('Manufacturing / Industrial Percentage', blank=True, null=True, help_text='In percent.')
    whspct = models.FloatField('Warehouse / Trucking Percentage', blank=True, null=True, help_text='In percent.')
    rndpct = models.FloatField('Lab / R & D  Percentage', blank=True, null=True, help_text='In percent.')
    edinstpct = models.FloatField('Edu / Institution Percentage)', blank=True, null=True, help_text='In percent.')
    othpct = models.FloatField('Other', blank=True, null=True, help_text='In percent.')
    hotelrms = models.FloatField('Hotel Rooms', blank=True, null=True)

    mfdisc = models.FloatField('Metro Future Discount', blank=True, null=True, help_text='In percent.')
    projecttype_detail = models.TextField('Project Type Detail', blank=True, null=True)
    
    description = models.TextField('description', blank=True, null=True)
    url = models.URLField('Project Website', blank=True, null=True, verify_exists=False)
    mapcintrnl = models.TextField('MAPC Internal Comments', blank=True, null=True)
    otheremprat2 = models.FloatField(blank=True, null=True)

    # new
    projecttype = models.ForeignKey(ProjectType, null=True)
    stalled = models.BooleanField('Stalled')
    phased = models.BooleanField('Phased')
    dev_name = models.CharField('Developer Name', blank=True, null=True, max_length=100)
    url_add = models.URLField('Additional Website', blank=True, null=True, verify_exists=False)
    affordable_comment = models.TextField('Affordability Comment', blank=True, null=True)
    parking_spaces = models.IntegerField('Parking Spaces', blank=True, null=True)
    as_of_right = models.NullBooleanField('As Of Right', blank=True, null=True)
    walkscore = models.ForeignKey(WalkScore, null=True, blank=True)
    todstation = models.ForeignKey(TODStation, null=True, blank=True)
    total_cost = models.IntegerField('Total Cost', blank=True, null=True)
    total_cost_allocated_pct = models.FloatField('Funding Allocated', blank=True, null=True, help_text='In percent.')
    draft = models.BooleanField(help_text='Required project information is incomplete.')
    removed = models.BooleanField(help_text='Deleted project, will not be shown on public page')    

    # internal
    created_by = models.ForeignKey(User, editable=False, blank=True, null=True, related_name='project_created_by')
    created = models.DateTimeField(auto_now_add=True)
    last_modified_by = models.ForeignKey(User, editable=False, blank=True, null=True, related_name='project_last_modified_by')
    last_modified = models.DateTimeField(auto_now=True)

    # tmp
    xcoord = models.FloatField(blank=True, null=True)
    ycoord = models.FloatField(blank=True, null=True)

    # geometry
    location = models.PointField(srid=26986, blank=True, null=True) # SRS mass state plane
    objects = models.GeoManager()
    
    class Meta:
        ordering = ['dd_id', ]

    def save(self, *args, **kwargs):

        # set TAZ
        try:
            self.taz = Taz.objects.get(geometry__contains=self.location)
        except Taz.DoesNotExist:
            self.taz = None 

        # set TOD station
        try:
            self.todstation = TODStation.objects.get(geometry__contains=self.location)
        except TODStation.DoesNotExist:
            self.todstation = None

        # the free walkscore api is limited to 1000 requests per day
        # update walkscore only on new or moved projects
        udate_walkscore = kwargs.pop('update_walkscore', None)
        if udate_walkscore == True:
            # get walkscore
            self.walkscore = self.get_walkscore()

        super(Project, self).save(*args, **kwargs)

    def __unicode__(self):
        return self.ddname

    def municipality(self):
        return self.taz.municipality

    def get_zipcode(self):
        try:
            zipcode = ZipCode.objects.get(geometry__contains=self.location)
        except ZipCode.DoesNotExist:
            zipcode = None
        return zipcode


    @models.permalink
    def get_absolute_url(self):
        return ('development.views.detail', None, { 'dd_id': self.dd_id, })

    def get_verbose_field_name(self, field):
        return self._meta.get_field_by_name(field)[0].verbose_name

    def get_walkscore(self):
        """ Gets walkscore from API, limited to 1000 requests per day 
        Example response:
        {
            "status": 1,
            "walkscore": 38,
            "description": "Car-Dependent",
            "updated": "2012-08-13 19:00:20.819797",
            "logo_url": "http://www2.walkscore.com/images/api-logo.gif",
            "more_info_icon": "http://www2.walkscore.com/images/api-more-info.gif",
            "more_info_link": "http://www.walkscore.com/how-it-works.shtml",
            "ws_link": "http://www.walkscore.com/score/Boxborough-MA-01719/lat=42.480611424525264/lng=-71.516146659851088/?utm_source=mapc.org&utm_medium=ws_api&utm_campaign=ws_api",
            "snapped_lat": 42.4800,
            "snapped_lon": -71.5155
        }
        """

        point = self.location
        point.transform(4326)
        address = ''
        zipcode = self.get_zipcode()
        if zipcode:
            address = zipcode.address

        ws_params = {
            'format': 'json', 
            'address': address, 
            'lat': point.y, 
            'lon': point.x, 
            'wsapikey': settings.WSAPIKEY
        }
        ws_request = requests.get('http://api.walkscore.com/score', params=ws_params)

        # check if we have good response
        if ws_request.json['status'] == 1:
            walkscore = WalkScore.objects.get_or_create(
                status = ws_request.json['status'],
                walkscore = ws_request.json['walkscore'],
                description = ws_request.json['description'],
                updated = pytz.UTC.localize(parse_datetime(ws_request.json['updated'])), # assume UTC
                ws_link = ws_request.json['ws_link'],
                snapped_lat = ws_request.json['snapped_lat'],
                snapped_lon = ws_request.json['snapped_lon']
            )
            return walkscore[0]
        else:
            return None


reversion.register(Project)
