# -*- coding: utf-8 -*-

# Copyright 2015 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
from oslo_config import cfg

from arsenal.director import scheduler
from arsenal.strategy import base as sb
from arsenal.tests.unit import base

CONF = cfg.CONF


def strat_directive_mock():
    return [
        sb.CacheNode('node-a', 'image-a', 'checksum-a'),
        sb.CacheNode('node-b', 'image-b', 'checksum-b'),
        sb.CacheNode('node-c', 'image-c', 'checksum-c'),
        sb.CacheNode('node-d', 'image-d', 'checksum-d'),
        sb.CacheNode('node-e', 'image-e', 'checksum-e'),
        sb.EjectNode('node-f'),
        sb.EjectNode('node-g'),
        sb.EjectNode('node-h'),
        sb.EjectNode('node-i'),
        sb.EjectNode('node-J'),
    ]

FAKE_FLAVOR_DATA = [
    sb.FlavorInput('io-flavor', lambda n: True),
    sb.FlavorInput('memory-flavor', lambda n: True),
    sb.FlavorInput('cpu-flavor', lambda n: True)
]

FAKE_IMAGE_DATA = [
    sb.ImageInput('Ubuntu', 'aaaa', 'ubuntu-checksum'),
    sb.ImageInput('CoreOS', 'aaaa', 'coreos-checksum'),
    sb.ImageInput('ArchLinux', 'aaaa', 'archlinux-checksum')
]

FAKE_NODE_DATA = [
    sb.NodeInput('abcd', 'io-flavor', False, False),
    sb.NodeInput('hjkl', 'memory-flavor', False, False),
    sb.NodeInput('asdf', 'compute-flavor', False, False)
]


class TestScheduler(base.TestCase):

    @mock.patch.object(scheduler.DirectorScheduler, 'periodic_tasks')
    @mock.patch('arsenal.director.onmetal_scout.OnMetalV1Scout')
    def setUp(self, onmetal_scout_mock, periodic_task_mock):
        super(TestScheduler, self).setUp()
        CONF.set_override('scout', 'onmetal_scout.OnMetalV1Scout', 'director')
        CONF.set_override('dry_run', False, 'director')
        # Make sure both rate limiters are off at the beginning of the test.
        CONF.set_override('cache_directive_rate_limit', 0, 'director')
        CONF.set_override('eject_directive_rate_limit', 0, 'director')

        onmetal_scout_mock.retrieve_node_data = mock.Mock()
        onmetal_scout_mock.retrieve_node_data.return_value = FAKE_NODE_DATA
        self.onmetal_scout_mock = onmetal_scout_mock

        self.scheduler = scheduler.DirectorScheduler()
        self.scheduler.scout = onmetal_scout_mock
        self.scheduler.node_data = FAKE_NODE_DATA
        self.scheduler.flavor_data = FAKE_FLAVOR_DATA
        self.scheduler.image_data = FAKE_IMAGE_DATA
        self.scheduler.strat.directives = strat_directive_mock
        self.issue_action_mock = mock.MagicMock()
        self.scheduler.scout.issue_action = self.issue_action_mock

    def test_cache_rate_limit_on(self):
        CONF.set_override('cache_directive_rate_limit', 2, 'director')
        self.scheduler.cache_rate_limiter = (
            scheduler.get_configured_cache_rate_limiter())
        self.assertIsNotNone(self.scheduler.cache_rate_limiter)
        self.scheduler.issue_directives(None)
        # 2 cache node directives, plus 5 eject node directives
        self.assertEqual(7, self.issue_action_mock.call_count)

    def test_cache_rate_limit_off(self):
        CONF.set_override('cache_directive_rate_limit', 0, 'director')
        self.scheduler.cache_rate_limiter = (
            scheduler.get_configured_cache_rate_limiter())
        self.assertIsNone(self.scheduler.cache_rate_limiter)
        self.scheduler.issue_directives(None)
        # 5 cache node directives, plus 5 eject node directives
        self.assertEqual(10, self.issue_action_mock.call_count)

    def test_eject_rate_limit_on(self):
        CONF.set_override('eject_directive_rate_limit', 2, 'director')
        self.scheduler.eject_rate_limiter = (
            scheduler.get_configured_ejection_rate_limiter())
        self.assertIsNotNone(self.scheduler.eject_rate_limiter)
        self.scheduler.issue_directives(None)
        # 2 eject node directives, plus 5 cache node directives
        self.assertEqual(7, self.issue_action_mock.call_count)

    def test_eject_rate_limit_off(self):
        CONF.set_override('eject_directive_rate_limit', 0, 'director')
        self.scheduler.eject_rate_limiter = (
            scheduler.get_configured_ejection_rate_limiter())
        self.assertIsNone(self.scheduler.eject_rate_limiter)
        self.scheduler.issue_directives(None)
        # 5 eject node directives, plus 5 cache node directives
        self.assertEqual(10, self.issue_action_mock.call_count)

    def test_both_rate_limit_on(self):
        CONF.set_override('cache_directive_rate_limit', 3, 'director')
        self.scheduler.cache_rate_limiter = (
            scheduler.get_configured_cache_rate_limiter())
        self.assertIsNotNone(self.scheduler.cache_rate_limiter)

        CONF.set_override('eject_directive_rate_limit', 3, 'director')
        self.scheduler.eject_rate_limiter = (
            scheduler.get_configured_ejection_rate_limiter())
        self.assertIsNotNone(self.scheduler.eject_rate_limiter)

        self.scheduler.issue_directives(None)
        # 3 eject node directives, plus 3 cache node directives
        self.assertEqual(6, self.issue_action_mock.call_count)

    def test_dry_run_on(self):
        # Dry-run enabled, so issue_action should not be called on the scout.
        CONF.set_override('dry_run', True, 'director')
        self.scheduler.issue_directives(None)
        self.assertFalse(self.issue_action_mock.called)

    def test_dry_run_off(self):
        # Dry-run disabled, so issue_action will be called.
        CONF.set_override('dry_run', False, 'director')
        self.scheduler.issue_directives(None)
        self.assertTrue(self.issue_action_mock.called)

    @mock.patch('arsenal.strategy.base.log_overall_node_statistics')
    def test_log_statistics_on(self, log_mock):
        CONF.set_override('log_statistics', True, 'director')
        self.scheduler.issue_directives(None)
        self.assertTrue(log_mock.called)

    @mock.patch('arsenal.strategy.base.log_overall_node_statistics')
    def test_log_statistics_off(self, log_mock):
        CONF.set_override('log_statistics', False, 'director')
        self.scheduler.issue_directives(None)
        self.assertFalse(log_mock.called)

    def test_issue_directives_empty_data_causes_strategy_suspension(self):
        self.scheduler.node_data = []
        self.scheduler.flavor_data = FAKE_FLAVOR_DATA
        self.scheduler.image_data = FAKE_IMAGE_DATA

        suspension_test_cases = (([], FAKE_FLAVOR_DATA, FAKE_IMAGE_DATA),
                                 (FAKE_NODE_DATA, [], FAKE_IMAGE_DATA),
                                 (FAKE_NODE_DATA, FAKE_FLAVOR_DATA, []),
                                 ([], [], FAKE_IMAGE_DATA),
                                 (FAKE_NODE_DATA, [], []))

        for case in suspension_test_cases:
            self.onmetal_scout_mock.retrieve_node_data.return_value = case[0]
            self.scheduler.flavor_data = case[1]
            self.scheduler.image_data = case[2]
            self.scheduler.strat.directives = mock.Mock()

            self.scheduler.issue_directives(None)

            self.assertFalse(self.scheduler.strat.directives.called)
