from ignition.service.framework import Capability, Service, interface
from ignition.service.config import ConfigurationPropertiesGroup, ConfigurationProperties
from ignition.service.api import BaseController
from ignition.model.failure import FailureDetails, FAILURE_CODE_INTERNAL_ERROR
from ignition.model.lifecycle import LifecycleExecution, LifecycleExecuteResponse, lifecycle_execution_dict, lifecycle_execute_response_dict, STATUS_COMPLETE, STATUS_FAILED
from ignition.model.references import FindReferenceResponse, FindReferenceResult, find_reference_response_dict
from ignition.model.associated_topology import AssociatedTopology
from ignition.service.messaging import Message, Envelope, JsonContent, TopicConfigProperties
from ignition.service.requestqueue import MAX_POLL_INTERVAL
#from ignition.service.requestqueue import REQUEST_MESSAGE_VERSION
from ignition.utils.file import DirectoryTree
from ignition.api.exceptions import ApiException
from ignition.service.logging import logging_context
from ignition.utils.propvaluemap import PropValueMap
import uuid
import logging
import os
import zipfile
import shutil
import base64
import pathlib
import ignition.openapi as openapi
import connexion

logger = logging.getLogger(__name__)
# Grabs the __init__.py from the openapi package then takes it's parent, the openapi directory itself
openapi_path = str(pathlib.Path(openapi.__file__).parent.resolve())


class ResourceDriverError(ApiException):
    status_code = 500

class UnreachableDeploymentLocationError(ResourceDriverError):
    status_code = 400

class InvalidRequestError(ResourceDriverError):
    status_code = 400

class TemporaryResourceDriverError(ResourceDriverError):
    status_code = 503

class InfrastructureNotFoundError(ResourceDriverError):
    status_code = 400

class RequestNotFoundError(ResourceDriverError):
    status_code = 400

class InvalidDriverFilesError(ResourceDriverError):
    status_code = 400

class InvalidLifecycleNameError(ResourceDriverError):
    status_code = 400


class ResourceDriverProperties(ConfigurationPropertiesGroup, Service, Capability):

    def __init__(self):
        super().__init__('resource_driver')
        self.api_spec = os.path.join(openapi_path, 'resource-driver.yaml')
        self.async_messaging_enabled = True
        self.scripts_workspace = './scripts_workspace'
        self.lifecycle_request_queue = LifecycleRequestQueueProperties()


class LifecycleRequestQueueProperties(ConfigurationProperties, Service, Capability):
    """
    Configuration related to the request queue

    Attributes:
    - enabled:
            is the request queue enabled?
    - group_id:
            Kafka consumer group_id for the request queue
                (default: request_queue_consumer)
    - topic:
            Kafka request queue topic configuration
    """

    def __init__(self):
        self.enabled = False
        self.group_id = "request_queue_consumer"
        self.max_poll_interval_ms = MAX_POLL_INTERVAL
        # name intentionally not set so that it can be constructed per-driver
        self.topic = TopicConfigProperties(auto_create=True, num_partitions=20, config={'retention.ms': 60000, 'message.timestamp.difference.max.ms': 60000, 'file.delete.delay.ms': 60000})
        self.failed_topic = TopicConfigProperties(auto_create=True, num_partitions=1, config={})


class ResourceDriverHandlerCapability(Capability):

    @interface
    def execute_lifecycle(self, lifecycle_name, driver_files, system_properties, resource_properties, request_properties, associated_topology, deployment_location):
        """
        Execute a lifecycle transition/operation for a Resource.
        This method should return immediate response of the request being accepted,
        it is expected that the ResourceDriverService will poll get_lifecycle_execution on this driver to determine when the request has completed (or devise your own method).

        :param str lifecycle_name: name of the lifecycle transition/operation to execute
        :param ignition.utils.file.DirectoryTree driver_files: object for navigating the directory intended for this driver from the Resource package. The user should call "remove_all" when the files are no longer needed
        :param ignition.utils.propvaluemap.PropValueMap system_properties: properties generated by LM for this Resource: resourceId, resourceName, requestId, metricKey, resourceManagerId, deploymentLocation, resourceType
        :param ignition.utils.propvaluemap.PropValueMap resource_properties: property values of the Resource
        :param ignition.utils.propvaluemap.PropValueMap request_properties: property values of this request
        :param ignition.model.associated_topology.AssociatedTopology associated_topology: 3rd party resources associated to the Resource, from any previous transition/operation requests
        :param dict deployment_location: the deployment location the Resource is assigned to
        :return: an ignition.model.lifecycle.LifecycleExecuteResponse

        :raises:
            ignition.service.resourcedriver.InvalidDriverFilesError: if the scripts are not valid
            ignition.service.resourcedriver.InvalidRequestError: if the request is invalid e.g. if no script can be found to execute the transition/operation given by lifecycle_name
            ignition.service.resourcedriver.TemporaryResourceDriverError: there is an issue handling this request at this time
            ignition.service.resourcedriver.ResourceDriverError: there was an error handling this request
        """
        pass

    @interface
    def get_lifecycle_execution(self, request_id, deployment_location):
        """
        Retrieve the status of a lifecycle transition/operation request

        :param str request_id: identifier of the request to check
        :param dict deployment_location: the deployment location the Resource is assigned to
        :return: an ignition.model.lifecycle.LifecycleExecution

        :raises:
            ignition.service.resourcedriver.RequestNotFoundError: if no request with the given request_id exists
            ignition.service.resourcedriver.TemporaryResourceDriverError: there is an issue handling this request at this time, an attempt should be made again at a later time
            ignition.service.resourcedriver.ResourceDriverError: there was an error handling this request
        """
        pass

    @interface
    def find_reference(self, instance_name, driver_files, deployment_location):
        """
        Find a Resource, returning the necessary property output values and internal resources from those instances

        :param str instance_name: name used to filter the Resource to find
        :param ignition.utils.file.DirectoryTree driver_files: object for navigating the directory intended for this driver from the Resource package. The user should call "remove_all" when the files are no longer needed
        :param dict deployment_location: the deployment location to find the instance in
        :return: an ignition.model.references.FindReferenceResponse

        :raises:
            ignition.service.resourcedriver.InvalidDriverFilesError: if the scripts are not valid
            ignition.service.resourcedriver.InvalidRequestError: if the request is invalid e.g. if no script can be found to execute the transition/operation given by lifecycle_name
            ignition.service.resourcedriver.TemporaryResourceDriverError: there is an issue handling this request at this time
            ignition.service.resourcedriver.ResourceDriverError: there was an error handling this request
        """

class ResourceDriverApiCapability(Capability):

    @interface
    def execute_lifecycle(self, **kwarg):
        pass

    @interface
    def find_reference(self, **kwarg):
        pass

class ResourceDriverServiceCapability(Capability):

    @interface
    def execute_lifecycle(self, lifecycle_name, driver_files, system_properties, resource_properties, request_properties, associated_topology, deployment_location):
        pass

    @interface
    def find_reference(self, instance_name, driver_files, deployment_location):
        pass

class DriverFilesManagerCapability(Capability):

    @interface
    def build_tree(self, tree_name, driver_files):
        pass


class LifecycleExecutionMonitoringCapability(Capability):

    @interface
    def monitor_execution(self, request_id, deployment_location):
        pass


class LifecycleMessagingCapability(Capability):

    @interface
    def send_lifecycle_execution(self, execution_task):
        pass


class ResourceDriverApiService(Service, ResourceDriverApiCapability, BaseController):
    """
    Out-of-the-box controller for the Lifecycle API
    """

    def __init__(self, **kwargs):
        if 'service' not in kwargs:
            raise ValueError('No service instance provided')
        self.service = kwargs.get('service')

    def execute_lifecycle(self, **kwarg):
        try:
            logging_context.set_from_headers()

            tenant_id=None
            if('tenantId' in connexion.request.headers):
                tenant_id = connexion.request.headers['tenantId']
                logger.debug("tenantId received in headers : %s", tenant_id)

            logger.debug("Value of tenantId is %s", tenant_id)
            body = self.get_body(kwarg)
            logger.debug('Handling lifecycle execution request with body %s', body)
            lifecycle_name = self.get_body_required_field(body, 'lifecycleName')
            driver_files = self.get_body_required_field(body, 'driverFiles')
            system_properties = self.get_body_required_field(body, 'systemProperties')
            resource_properties = self.get_body_field(body, 'resourceProperties', {})
            request_properties = self.get_body_field(body, 'requestProperties', {})
            associated_topology = self.get_body_field(body, 'associatedTopology', {})
            deployment_location = self.get_body_required_field(body, 'deploymentLocation')
            execute_response = self.service.execute_lifecycle(lifecycle_name, driver_files, system_properties, resource_properties, request_properties, associated_topology, deployment_location, tenant_id)
            response = lifecycle_execute_response_dict(execute_response)
            if(tenant_id is not None):
                return (response, 202, {'tenantId': tenant_id})
            else:
                return (response, 202)
        finally:
            logging_context.clear()

    def find_reference(self, **kwarg):
        try:
            logging_context.set_from_headers()

            body = self.get_body(kwarg)
            logger.debug('Handling find reference request with body %s', body)
            instance_name = self.get_body_required_field(body, 'instanceName')
            driver_files = self.get_body_required_field(body, 'driverFiles')
            deployment_location = self.get_body_required_field(body, 'deploymentLocation')
            service_find_response = self.service.find_reference(instance_name, driver_files, deployment_location)
            response = find_reference_response_dict(service_find_response)
            return (response, 200)
        finally:
            logging_context.clear()


class ResourceDriverService(Service, ResourceDriverServiceCapability):
    """
    Out-of-the-box service for the Lifecycle API
    """

    def __init__(self, **kwargs):
        if 'handler' not in kwargs:
            raise ValueError('handler argument not provided')
        if 'resource_driver_config' not in kwargs:
            raise ValueError('resource_driver_config argument not provided')
        if 'driver_files_manager' not in kwargs:
            raise ValueError('driver_files_manager argument not provided')
        self.handler = kwargs.get('handler')
        self.driver_files_manager = kwargs.get('driver_files_manager')
        resource_driver_config = kwargs.get('resource_driver_config')
        self.async_enabled = resource_driver_config.async_messaging_enabled
        if self.async_enabled is True:
            if 'lifecycle_monitor_service' not in kwargs:
                raise ValueError('lifecycle_monitor_service argument not provided (required when async_messaging_enabled is True)')
            self.lifecycle_monitor_service = kwargs.get('lifecycle_monitor_service')
        self.async_requests_enabled = resource_driver_config.lifecycle_request_queue.enabled
        if self.async_requests_enabled:
            if 'lifecycle_request_queue' not in kwargs:
                raise ValueError('lifecycle_request_queue argument not provided (required when lifecycle_request_queue.enabled is True)')
            self.lifecycle_request_queue = kwargs.get('lifecycle_request_queue')

    def execute_lifecycle(self, lifecycle_name, driver_files, system_properties, resource_properties, request_properties, associated_topology, deployment_location, tenant_id):
        if self.async_requests_enabled:
            request_id = str(uuid.uuid4())
            self.lifecycle_request_queue.queue_lifecycle_request({
                'request_id': request_id,
                'lifecycle_name': lifecycle_name,
                'driver_files': driver_files,
                'system_properties': system_properties,
                'resource_properties': resource_properties,
                'request_properties': request_properties,
                'associated_topology': associated_topology,
                'deployment_location': deployment_location,
                'tenant_id': tenant_id,
                'logging_context': dict(logging_context.get_all())
            })
            execute_response = LifecycleExecuteResponse(request_id)
        else:
            file_name = '{0}'.format(str(uuid.uuid4()))
            driver_files_tree = self.driver_files_manager.build_tree(file_name, driver_files)
            associated_topology = AssociatedTopology.from_dict(associated_topology)
            execute_response = self.handler.execute_lifecycle(lifecycle_name, driver_files_tree, PropValueMap(system_properties), PropValueMap(resource_properties), PropValueMap(request_properties), associated_topology, deployment_location)
            if self.async_enabled is True:
                self.__async_lifecycle_execution_completion(execute_response.request_id, deployment_location, tenant_id)
        return execute_response

    def find_reference(self, instance_name, driver_files, deployment_location):
        file_name = '{0}'.format(str(uuid.uuid4()))
        driver_files_tree = self.driver_files_manager.build_tree(file_name, driver_files)
        find_response = self.handler.find_reference(instance_name, driver_files_tree, deployment_location)
        return find_response

    def __async_lifecycle_execution_completion(self, request_id, deployment_location, tenant_id):
        self.lifecycle_monitor_service.monitor_execution(request_id, deployment_location, tenant_id)


LIFECYCLE_EXECUTION_MONITOR_JOB_TYPE = 'LifecycleExecutionMonitoring'


class LifecycleExecutionMonitoringService(Service, LifecycleExecutionMonitoringCapability):

    def __init__(self, **kwargs):
        if 'job_queue_service' not in kwargs:
            raise ValueError('job_queue_service argument not provided')
        if 'lifecycle_messaging_service' not in kwargs:
            raise ValueError('lifecycle_messaging_service argument not provided')
        if 'handler' not in kwargs:
            raise ValueError('handler argument not provided')
        self.job_queue_service = kwargs.get('job_queue_service')
        self.lifecycle_messaging_service = kwargs.get('lifecycle_messaging_service')
        self.handler = kwargs.get('handler')
        self.job_queue_service.register_job_handler(LIFECYCLE_EXECUTION_MONITOR_JOB_TYPE, self.job_handler)

    def job_handler(self, job_definition):
        if 'request_id' not in job_definition or job_definition['request_id'] is None:
            logger.warning('Job with {0} job type is missing request_id. This job has been discarded'.format(LIFECYCLE_EXECUTION_MONITOR_JOB_TYPE))
            return True
        if 'deployment_location' not in job_definition or job_definition['deployment_location'] is None:
            logger.warning('Job with {0} job type is missing deployment_location. This job has been discarded'.format(LIFECYCLE_EXECUTION_MONITOR_JOB_TYPE))
            return True
        request_id = job_definition['request_id']
        deployment_location = job_definition['deployment_location']
        tenant_id = job_definition['tenant_id']
        try:
            lifecycle_execution_task = self.handler.get_lifecycle_execution(request_id, deployment_location)
        except RequestNotFoundError as e:
            logger.debug('Request with ID {0} not found, the request will no longer be monitored'.format(request_id))
            return True
        except TemporaryResourceDriverError as e:
            logger.exception('Temporary error occurred checking status of request with ID {0}. The job will be re-queued: {1}'.format(request_id, str(e)))
            return False
        except Exception as e:
            logger.exception('Unexpected error occurred checking status of request with ID {0}. A failure response will be posted and the job will NOT be re-queued: {1}'.format(request_id, str(e)))
            lifecycle_execution_task = LifecycleExecution(request_id, STATUS_FAILED, FailureDetails(FAILURE_CODE_INTERNAL_ERROR, str(e)))
            self.lifecycle_messaging_service.send_lifecycle_execution(lifecycle_execution_task, tenant_id=tenant_id)
            return True
        status = lifecycle_execution_task.status
        if status in [STATUS_COMPLETE, STATUS_FAILED]:
            self.lifecycle_messaging_service.send_lifecycle_execution(lifecycle_execution_task, tenant_id=tenant_id)
            if hasattr(self.handler, 'post_lifecycle_response'):
                try:
                    logger.debug(f'Calling post_lifecycle_response for request with ID: {0}'.format(request_id))
                    self.handler.post_lifecycle_response(request_id, deployment_location)
                except Exception as e:
                    logger.exception('Unexpected error occurred on post_lifecycle_response for request with ID {0}. This error has no impact on the response: {1}'.format(request_id, str(e)))
            return True
        return False

    def __create_job_definition(self, request_id, deployment_location, tenant_id):
        return {
            'job_type': LIFECYCLE_EXECUTION_MONITOR_JOB_TYPE,
            'request_id': request_id,
            'deployment_location': deployment_location,
            'tenant_id': tenant_id
        }

    def monitor_execution(self, request_id, deployment_location, tenant_id):
        if request_id is None:
            raise ValueError('Cannot monitor task when request_id is not given')
        if deployment_location is None:
            raise ValueError('Cannot monitor task when deployment_location is not given')
        self.job_queue_service.queue_job(self.__create_job_definition(request_id, deployment_location, tenant_id))


class LifecycleMessagingService(Service, LifecycleMessagingCapability):

    def __init__(self, **kwargs):
        if 'postal_service' not in kwargs:
            raise ValueError('postal_service argument not provided')
        if 'topics_configuration' not in kwargs:
            raise ValueError('topics_configuration argument not provided')
        self.postal_service = kwargs.get('postal_service')
        topics_configuration = kwargs.get('topics_configuration')
        if topics_configuration.lifecycle_execution_events is None:
            raise ValueError('lifecycle_execution_events topic must be set')
        self.lifecycle_execution_events_topic = topics_configuration.lifecycle_execution_events.name
        if self.lifecycle_execution_events_topic is None:
            raise ValueError('lifecycle_execution_events topic name must be set')

    def send_lifecycle_execution(self, lifecycle_execution, **kwargs):
        tenant_id=None
        if 'tenant_id' in kwargs:
            tenant_id = kwargs['tenant_id'] 
        if lifecycle_execution is None:
            raise ValueError('lifecycle_execution must be set to send an lifecycle execution event')
        lifecycle_execution_message_content = lifecycle_execution_dict(lifecycle_execution)
        message_str = JsonContent(lifecycle_execution_message_content).get()
        self.postal_service.post(Envelope(self.lifecycle_execution_events_topic, Message(message_str), tenant_id=tenant_id))

class DriverFilesManagerService(Service, DriverFilesManagerCapability):

    def __init__(self, **kwargs):
        if 'resource_driver_config' not in kwargs:
            raise ValueError('resource_driver_config argument not provided')
        resource_driver_config = kwargs.get('resource_driver_config')
        self.scripts_workspace = resource_driver_config.scripts_workspace
        if self.scripts_workspace is None:
            raise ValueError('scripts_workspace directory must be set')
        self.__create_workspace_if_needed()

    def __create_workspace_if_needed(self):
        if not os.path.exists(self.scripts_workspace):
            os.makedirs(self.scripts_workspace)

    def build_tree(self, tree_name, lifecycle_scripts):
        self.__clear_existing_files(tree_name)
        package_path = self.__write_scripts_to_disk(tree_name, lifecycle_scripts)
        extracted_path = self.__extract_scripts(tree_name, package_path)
        return DirectoryTree(extracted_path)

    def __clear_existing_files(self, tree_name):
        package_write_path = self.__determine_package_path(tree_name)
        if os.path.exists(package_write_path):
            os.remove(package_write_path)
        extracted_path = self.__determine_extracted_path(tree_name)
        if os.path.exists(extracted_path):
            shutil.rmtree(extracted_path)

    def __determine_package_path(self, tree_name):
        package_write_path = os.path.join(self.scripts_workspace, '{0}.zip'.format(tree_name))
        return package_write_path

    def __determine_extracted_path(self, tree_name):
        extracted_path = os.path.join(self.scripts_workspace, tree_name)
        return extracted_path

    def __write_scripts_to_disk(self, tree_name, lifecycle_scripts):
        package_write_path = self.__determine_package_path(tree_name)
        with open(package_write_path, 'wb') as package_writer:
            package_writer.write(base64.b64decode(lifecycle_scripts))
        return package_write_path

    def __extract_scripts(self, tree_name, package_path):
        if not zipfile.is_zipfile(package_path):
            raise ValueError('lifecycle_scripts should include binary contents of a zip file')
        extracted_path = self.__determine_extracted_path(tree_name)
        with zipfile.ZipFile(package_path, 'r') as package_zip:
            package_zip.extractall(extracted_path)
        os.remove(package_path)
        return extracted_path
