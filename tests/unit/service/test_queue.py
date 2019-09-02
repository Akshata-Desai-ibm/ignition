import unittest
from unittest.mock import MagicMock
from ignition.service.queue import MessagingJobQueueService
from ignition.service.messaging import Envelope

class TestMessagingJobQueueService(unittest.TestCase):

    def setUp(self):
        self.mock_postal_service = MagicMock()
        self.mock_inbox_service = MagicMock()
        self.mock_topics_config = MagicMock(job_queue='job_queue')

    def test_init_without_postal_service_throws_error(self):
        with self.assertRaises(ValueError) as context:
            MessagingJobQueueService(inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        self.assertEqual(str(context.exception), 'postal_service argument not provided')

    def test_init_without_inbox_service_throws_error(self):
        with self.assertRaises(ValueError) as context:
            MessagingJobQueueService(postal_service=self.mock_postal_service, topics_config=self.mock_topics_config)
        self.assertEqual(str(context.exception), 'inbox_service argument not provided')

    def test_init_without_topics_config_throws_error(self):
        with self.assertRaises(ValueError) as context:
            MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service)
        self.assertEqual(str(context.exception), 'topics_config argument not provided')

    def test_init_without_job_queue_topic_throws_error(self):
        mock_topics_config = MagicMock(job_queue=None)
        with self.assertRaises(ValueError) as context:
            MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=mock_topics_config)
        self.assertEqual(str(context.exception), 'job_queue topic must be set')

    def test_init_configures_watch_on_job_queue_inbox(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        self.mock_inbox_service.watch_inbox.assert_called_once_with('job_queue', job_queue_service._MessagingJobQueueService__received_next_job_handler)

    def test_register_job_handler(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        mock_handler_func = MagicMock()
        job_queue_service.register_job_handler('test_job_type', mock_handler_func)
        self.assertEqual(job_queue_service.job_handlers['test_job_type'], mock_handler_func)

    def test_register_non_callable_job_handler(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        with self.assertRaises(ValueError) as context:
            job_queue_service.register_job_handler('test_job_type', 'not a func')
        self.assertEqual(str(context.exception), 'handler_func argument must be a callable function')

    def test_register_duplicate_job_type_handler(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        job_queue_service.register_job_handler('test_job_type', MagicMock())
        with self.assertRaises(ValueError) as context:
            job_queue_service.register_job_handler('test_job_type', MagicMock())
        self.assertEqual(str(context.exception), 'Handler for job_type \'test_job_type\' has already been registered')

    def test_queue_job_posts_message(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        job_queue_service.queue_job({'job_type': 'test_job'})
        self.mock_postal_service.post.assert_called_once()
        args, kwargs = self.mock_postal_service.post.call_args
        self.assertEqual(len(args), 1)
        envelope_arg = args[0]
        self.assertIsInstance(envelope_arg, Envelope)
        self.assertEqual(envelope_arg.address, 'job_queue')
        self.assertEqual(envelope_arg.message.content, b'{"job_type": "test_job"}')

    def test_queue_job_without_type_throws_error(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        with self.assertRaises(ValueError) as context:
            job_queue_service.queue_job({})
        self.assertEqual(str(context.exception), 'job_definition must have a job_type key')
        with self.assertRaises(ValueError) as context:
            job_queue_service.queue_job({'job_type': None})
        self.assertEqual(str(context.exception), 'job_definition must have a job_type value (not None)')
        
    def test_next_job_handler_calls_handler_func(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        mock_handler_func = MagicMock()
        job_queue_service.register_job_handler('test_job', mock_handler_func)
        job_queue_service._MessagingJobQueueService__received_next_job_handler('{"job_type": "test_job"}')
        mock_handler_func.assert_called_once_with({'job_type': 'test_job'})

    def test_next_job_handler_requeues_job_if_handler_func_returns_not_finished(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        mock_handler_func = MagicMock()
        mock_handler_func.return_value = False
        job_queue_service.register_job_handler('test_job', mock_handler_func)
        job_queue_service._MessagingJobQueueService__received_next_job_handler('{"job_type": "test_job"}')
        mock_handler_func.assert_called_once_with({'job_type': 'test_job'})
        self.mock_postal_service.post.assert_called_once()
        args, kwargs = self.mock_postal_service.post.call_args
        self.assertEqual(len(args), 1)
        envelope_arg = args[0]
        self.assertIsInstance(envelope_arg, Envelope)
        self.assertEqual(envelope_arg.address, 'job_queue')
        self.assertEqual(envelope_arg.message.content, b'{"job_type": "test_job"}')

    def test_next_job_handler_does_not_requeue_job_when_finished(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        mock_handler_func = MagicMock()
        mock_handler_func.return_value = True
        job_queue_service.register_job_handler('test_job', mock_handler_func)
        job_queue_service._MessagingJobQueueService__received_next_job_handler('{"job_type": "test_job"}')
        mock_handler_func.assert_called_once_with({'job_type': 'test_job'})
        self.mock_postal_service.post.assert_not_called()

    def test_next_job_handler_does_nothing_when_no_job_type(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        mock_handler_func = MagicMock()
        mock_handler_func.return_value = True
        job_queue_service.register_job_handler('test_job', mock_handler_func)
        job_queue_service._MessagingJobQueueService__received_next_job_handler('{"not_job_type": "test_job"}')
        self.mock_postal_service.post.assert_not_called()
        
    def test_next_job_handler_requeues_job_when_no_handler_registered(self):
        job_queue_service = MessagingJobQueueService(postal_service=self.mock_postal_service, inbox_service=self.mock_inbox_service, topics_config=self.mock_topics_config)
        job_queue_service._MessagingJobQueueService__received_next_job_handler('{"job_type": "test_job"}')
        self.mock_postal_service.post.assert_called_once()
        args, kwargs = self.mock_postal_service.post.call_args
        self.assertEqual(len(args), 1)
        envelope_arg = args[0]
        self.assertIsInstance(envelope_arg, Envelope)
        self.assertEqual(envelope_arg.address, 'job_queue')
        self.assertEqual(envelope_arg.message.content, b'{"job_type": "test_job"}')