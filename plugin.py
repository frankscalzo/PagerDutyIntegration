from DivvyPlugins.plugin_metadata import PluginMetadata
from DivvyBotfactory.registry import BotFactoryRegistryWrapper
from DivvyUtils.field_definition import StringField
from DivvyUtils import web_requests
import simplejson as json
import DivvyDb

import logging  # TODO


registry = BotFactoryRegistryWrapper()

es_doc_type = 'PagerDutyIncident'
es_index_name = 'divvy.pagerduty'
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


class metadata(PluginMetadata):
    """
    Information about this plugin
    """
    version = '1.0'
    last_updated_date = '2016-06-13'
    author = 'DivvyCloud Inc.'
    nickname = 'PagerDuty Integration'
    default_language_description = 'Send alerts to PagerDuty.'
    support_email = 'support@divvycloud.com'
    support_url = 'http://support.divvycloud.com'
    main_url = 'http://www.divvycloud.com'
    category = 'Integrations'
    managed = False



# TODO: Make these not this way
# api_url = 'dcengineering.pagerduty.com'
api_url = 'https://events.pagerduty.com/generic/2010-04-15/create_event.json'
api_key = 'secret'
client_url = 'http://www.divvycloud.com'

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
    incident_key = ';'.join((str(bot.resource_id), str(event.resource.resource_id)))
    description = settings.get('description', 'Event created by DivvyCloud application.')
    headers = {
        'Content-type': 'application/json',
        'Authorization': 'Token token=' + api_key,
    }
    payload = json.dumps({
        'service_key': 'secret',
        'event_type': 'trigger',
        'incident_key': incident_key,
        'description': description,  # TODO: Templating
        'details': {'test': 'test'},  # TODO: event info
        'client': 'DivvyCloud',
        'client_url': client_url,
        # 'contexts': []
    })
    # es_connection.index(
    #     index=es_index_name,
    #     doc_type=es_doc_type,
    #     body={
    #         'bot_resource_id': str(bot.resource_id),
    #         'resource_id': str(event.resource.resource_id),
    #         'description': description,
    #         'incident_key': None  # TODO
    #     }
    # )
    
    def upon_success(response):
        logging.error(response)
        logging.error(response.content)
    def upon_failure(response):
        logging.error(response)
        logging.error(response.content)
    
    web_requests.post_threaded(
        url=api_url,
        headers=headers,
        payload=payload,
        timeout=15,
        max_attempts=3,
        upon_success=upon_success,
        upon_failure=upon_failure
    )
def pager_duty_resolve(event, bot, settings):
    pass  # TODO
    


def load():
    registry.load()

def unload():
    registry.unload()
