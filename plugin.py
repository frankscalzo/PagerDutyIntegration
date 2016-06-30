import logging
import elasticsearch
import simplejson as json

from DivvyPlugins.plugin_metadata import PluginMetadata
from DivvyPlugins.settings import GlobalSetting
from DivvyResource.Resources import DivvyPlugin
from DivvyBotfactory.registry import BotFactoryRegistryWrapper
from DivvyUtils.field_definition import StringField
from DivvyUtils import web_requests
import DivvyDb



class metadata(PluginMetadata):
    """
    Information about this plugin
    """
    version = '1.0'
    last_updated_date = '2016-06-13'
    author = 'DivvyCloud Inc.'
    nickname = 'PagerDuty Integration'
    default_language_description = 'Trigger and resolve incidents with PagerDuty.'
    support_email = 'support@divvycloud.com'
    support_url = 'http://support.divvycloud.com'
    main_url = 'http://www.divvycloud.com'
    category = 'Integrations'
    managed = False



setting_client_url = GlobalSetting(
    name='divvy.pagerdutyintegration.client_url',
    display_name='Client URL',
    type_hint='string',
    description='Client URL to provide in incident trigger requests sent to PagerDuty.',
    default_value='https://events.pagerduty.com/generic/2010-04-15/create_event.json'
).get_for_resource(DivvyPlugin.get_current_plugin())
setting_api_url = GlobalSetting(
    name='divvy.pagerdutyintegration.api_url',
    display_name='PagerDuty API URL',
    type_hint='string',
    description='URL to send requests to regarding PagerDuty incidents.',
    default_value='https://events.pagerduty.com/generic/2010-04-15/create_event.json'
).get_for_resource(DivvyPlugin.get_current_plugin())
setting_api_key = GlobalSetting(
    name='divvy.pagerdutyintegration.api_key',
    display_name='PagerDuty API Key',
    type_hint='password',
    description='API key generated in the API Access section of PagerDuty configuration.'
).get_for_resource(DivvyPlugin.get_current_plugin())
setting_service_key = GlobalSetting(
    name='divvy.pagerdutyintegration.service_key',
    display_name='PagerDuty Service Key',
    type_hint='password',
    description='Service key generated in the Services section of PagerDuty configuration.'
).get_for_resource(DivvyPlugin.get_current_plugin())



logger = logging.getLogger('PagerDutyIntegration')

registry = BotFactoryRegistryWrapper()

es_doc_type = 'PagerDutyIncident'
es_index_name = 'divvy_pagerduty_incidents'
document_store = 'default'  # Name of documentstore configuration to use

es_connection = DivvyDb.Elasticsearch.get_connection(document_store)  # TODO: Use a tracker

DivvyDb.Elasticsearch.require_template(
    doc_store_name=document_store,
    template_name="pagerduty_template",
    template_data={
        "order": 0,
        "template": es_index_name,
        "mappings": {
            es_doc_type: {
                "_ttl": {
                    "enabled": True,
                    "default": "7d"
                },
                "properties": {
                    "bot_resource_id": {
                        "index": "not_analyzed",
                        "type": "string"
                    },
                    "resource_id": {
                        "index": "not_analyzed",
                        "type": "string"
                    },
                    "incident_key": {
                        "index": "not_analyzed",
                        "type": "string"
                    },
                    'description': {
                        "index": "not_analyzed",
                        "type": "string"
                    }
                }
            }
        }
    }
)



def get_incident_key(bot, event):
    """
    Construct an incident key from the bot and resource identifiers
    Having the same incident key for multiple hits on the same resources
    is interpreted as PagerDuty as an update upon the original incident.
    """
    return ';'.join(
        ('divvy', str(bot.resource_id), str(event.resource.resource_id))
    )
    
def get_headers():
    return {
        'Content-type': 'application/json',
        'Authorization': 'Token token=' + setting_api_key,
    }



@registry.action(
    uid = 'divvy.action.pager_duty_incident',
    name='PagerDuty Incident',
    description=(
        'Trigger an incident with PagerDuty and resolve that incident when the '
        'resource is found to no longer meet the conditions having caused the '
        'incident to be triggered in the first place.'
    ),
    author='DivvyCloud Inc.',
    supported_resources=[],
    settings_config=[
        StringField(
            name='description',
            display_name='Description',
            description='Description text to include with the triggered incident.'
        )
    ]
)
def pager_duty_trigger(event, bot, settings):
    incident_key = get_incident_key(bot, event)
    # Get a description string for the incident.
    description = settings.get(
        'description', 'Event created by DivvyCloud application.'
    )
    # Payload for the API call.
    payload = json.dumps({
        'service_key': setting_service_key,
        'event_type': 'trigger',
        'incident_key': incident_key,
        'description': description,
        'details': event._asdict(),
        'client': 'DivvyCloud',
        'client_url': setting_client_url,
    })
    # Callback to record in ES the triggered incident.
    def upon_success(response):
        es_connection.index(  # TODO: Batch using a tracker
            index=es_index_name,
            doc_type=es_doc_type,
            id=incident_key,
            body={
                'bot_resource_id': str(bot.resource_id),
                'resource_id': str(event.resource.resource_id),
                'description': description
            }
        )
    # Response failure callback.
    def upon_failure(response):
        logger.error('Failed to trigger PagerDuty incident %s.', incident_key)
        logger.error(response.content)
    # Actually make the API call.
    web_requests.post_threaded(
        url=setting_api_url,
        headers=get_headers(),
        payload=payload,
        upon_success=upon_success,
        upon_failure=upon_failure
    )

@registry.complement('divvy.action.pager_duty_incident')
def pager_duty_resolve(event, bot, settings):
    incident_key = get_incident_key(bot, event)
    try:
        result = es_connection.get(  # TODO: Batching
            index=es_index_name,
            doc_type=es_doc_type,
            id=incident_key,
            _source=False
        )
    except elasticsearch.exceptions.NotFoundError:
        pass  # Index doesn't exist yet
    else:
        if result is not None:
            # Get a description string for the incident.
            description = settings.get(
                'description', 'Event created by DivvyCloud application.'
            )
            payload = json.dumps({
                'service_key': setting_service_key,
                'event_type': 'resolve',
                'incident_key': incident_key,
                'description': 'Resolved: %s' % description,
                'details': event._asdict(),
                'client': 'DivvyCloud',
                'client_url': setting_client_url,
            })
            def upon_success(response):
                es_connection.delete(
                    index=es_index_name,
                    doc_type=es_doc_type,
                    id=incident_key
                )
            def upon_failure(response):
                logger.error('Failed to resolve PagerDuty incident %s.', incident_key)
                logger.error(response.content)
            web_requests.post_threaded(
                url=setting_api_url,
                headers=get_headers(),
                payload=payload,
                upon_success=upon_success,
                upon_failure=upon_failure
            )



def load():
    registry.load()

def unload():
    registry.unload()
