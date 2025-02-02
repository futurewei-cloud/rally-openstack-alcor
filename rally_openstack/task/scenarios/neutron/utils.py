# Copyright 2014: Intel Inc.
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

import random

from rally.common import cfg
from rally.common import logging
from rally import exceptions
from rally.task import atomic
from rally.task import utils

from rally_openstack.common.services.network import neutron
from rally_openstack.task import scenario


CONF = cfg.CONF


LOG = logging.getLogger(__name__)


class NeutronBaseScenario(scenario.OpenStackScenario):
    """Base class for Neutron scenarios with basic atomic actions."""

    def __init__(self, *args, **kwargs):
        super(NeutronBaseScenario, self).__init__(*args, **kwargs)
        if hasattr(self, "_clients"):
            self.neutron = neutron.NeutronService(
                clients=self._clients,
                name_generator=self.generate_random_name,
                atomic_inst=self.atomic_actions()
            )
        if hasattr(self, "_admin_clients"):
            self.admin_neutron = neutron.NeutronService(
                clients=self._admin_clients,
                name_generator=self.generate_random_name,
                atomic_inst=self.atomic_actions()
            )

    def _get_or_create_network(self, **network_create_args):
        """Get a network from context, or create a new one.

        This lets users either create networks with the 'network'
        context, provide existing networks with the 'existing_network'
        context, or let the scenario create a default network for
        them.
        """

        if "networks" in self.context["tenant"]:
            networks = self.context["tenant"]["networks"]
            net_idx = self.context["iteration"] % len(networks)
            return networks[net_idx]
        else:
            LOG.warning("Running this scenario without either the "
                        "'network@openstack' or 'existing_network@openstack' "
                        "context is deprecated since Rally-OpenStack 2.0.0.")
            return self.neutron.create_network(**network_create_args)


class NeutronScenario(NeutronBaseScenario):
    """Base class for Neutron scenarios with basic atomic actions."""

    # TODO(rkiran): modify in case LBaaS-v2 requires
    LB_METHOD = "ROUND_ROBIN"
    LB_PROTOCOL = "HTTP"
    LB_PROTOCOL_PORT = 80
    HM_TYPE = "PING"
    HM_MAX_RETRIES = 3
    HM_DELAY = 20
    HM_TIMEOUT = 10

    def _get_network_id(self, network, **kwargs):
        """Get Neutron network ID for the network name.

        :param network: str, network name/id
        :param kwargs: dict, network options
        :returns: str, Neutron network-id
        """
        try:
            return self.neutron.find_network(network)["id"]
        except exceptions.GetResourceFailure:
            raise exceptions.NotFoundException(
                message="Network %s not found." % network)

    @property
    def _ext_gw_mode_enabled(self):
        """Determine if the ext-gw-mode extension is enabled.

        Without this extension, we can't pass the enable_snat parameter.
        """
        return self.neutron.supports_extension("ext-gw-mode", silent=True)

    def _create_network(self, network_create_args):
        """Create neutron network.

        :param network_create_args: dict, POST /v2.0/networks request options
        :returns: neutron network dict
        """
        network_create_args.pop("name", None)
        return {"network": self.neutron.create_network(**network_create_args)}

    def _list_networks(self, **kwargs):
        """Return user networks list.

        :param kwargs: network list options
        """
        return self.neutron.list_networks(**kwargs)

    def _list_agents(self, **kwargs):
        """Fetches agents.

        :param kwargs: neutron agent list options
        :returns: user agents list
        """
        return self.neutron.list_agents(**kwargs)

    def _update_network(self, network, network_update_args):
        """Update the network.

        This atomic function updates the network with network_update_args.

        :param network: Network object
        :param network_update_args: dict, POST /v2.0/networks update options
        :returns: updated neutron network dict
        """
        network_update_args["name"] = self.generate_random_name()
        return {"network": self.neutron.update_network(
            network["network"]["id"], **network_update_args)}

    def _show_network(self, network, **kwargs):
        """show network details.

        :param network: Network object
        :param kwargs: dict, POST /v2.0/networks show options
        :returns: details of the network
        """
        network = self.neutron.get_network(network["network"]["id"], **kwargs)
        return {"network": network}

    def _delete_network(self, network):
        """Delete neutron network.

        :param network: Network object
        """
        self.neutron.delete_network(network["id"])

    def _create_subnet(self, network, subnet_create_args, start_cidr=None):
        """Create neutron subnet.

        :param network: neutron network dict
        :param subnet_create_args: POST /v2.0/subnets request options
        :returns: neutron subnet dict
        """

        subnet_create_args.pop("name", None)
        subnet_create_args["network_id"] = network["network"]["id"]
        subnet_create_args["start_cidr"] = start_cidr

        return {"subnet": self.neutron.create_subnet(**subnet_create_args)}

    def _list_subnets(self):
        """Returns user subnetworks list."""
        return self.neutron.list_subnets()

    def _show_subnet(self, subnet, **kwargs):
        """show subnet details.

        :param subnet: Subnet object
        :param kwargs: Optional additional arguments for subnet show
        :returns: details of the subnet
        """
        return {"subnet": self.neutron.get_subnet(subnet["subnet"]["id"])}

    def _update_subnet_routetable(self, subnet_id, routetable_args):
        return self.neutron.update_subnet_routetable(subnet_id, **routetable_args)

    def _delete_subnet_routetable(self, subnet_id):
        return self.neutron.delete_subnet_routetable(subnet_id)

    def _update_subnet(self, subnet, subnet_update_args):
        """Update the neutron subnet.

        This atomic function updates the subnet with subnet_update_args.

        :param subnet: Subnet object
        :param subnet_update_args: dict, PUT /v2.0/subnets update options
        :returns: updated neutron subnet dict
        """
        subnet_update_args["name"] = self.generate_random_name()
        return {"subnet": self.neutron.update_subnet(
            subnet["subnet"]["id"], **subnet_update_args)}

    def _delete_subnet(self, subnet):
        """Delete neutron subnet

        :param subnet: Subnet object
        """
        self.neutron.delete_subnet(subnet["subnet"]["id"])

    def _create_router(self, router_create_args, external_gw=False):
        """Create neutron router.

        :param router_create_args: POST /v2.0/routers request options
        :returns: neutron router dict
        """
        router_create_args.pop("name", None)
        if ("tenant_id" in router_create_args
                and "project_id" not in router_create_args):
            router_create_args["project_id"] = router_create_args.pop(
                "tenant_id")

        return {"router": self.neutron.create_router(
            discover_external_gw=external_gw, **router_create_args)}

    def _list_routers(self):
        """Returns user routers list."""
        return self.neutron.list_routers()

    def _show_router(self, router, **kwargs):
        """Show information of a given router.

        :param router: ID or name of router to look up
        :kwargs: dict, POST /v2.0/routers show options
        :return: details of the router
        """
        return {"router": self.neutron.get_router(
            router["router"]["id"], **kwargs)}

    def _delete_router(self, router):
        """Delete neutron router

        :param router: Router object
        """
        self.neutron.delete_router(router["router"]["id"])

    def _update_router(self, router, router_update_args):
        """Update the neutron router.

        This atomic function updates the router with router_update_args.

        :param router: dict, neutron router
        :param router_update_args: dict, PUT /v2.0/routers update options
        :returns: updated neutron router dict
        """
        router_update_args["name"] = self.generate_random_name()
        return {"router": self.neutron.update_router(
            router["router"]["id"], **router_update_args)}

    def _add_extra_routes(self, router, routes_args):
        return {"router": self.neutron.add_extra_routes_to_router(
            router["router"]["id"], **routes_args)}

    def _remove_extra_routes(self, router, routes_args):
        return {"router": self.neutron.remove_extra_routes_from_router(
            router["router"]["id"], **routes_args)}

    def _create_port(self, network, port_create_args):
        """Create neutron port.

        :param network: neutron network dict
        :param port_create_args: POST /v2.0/ports request options
        :returns: neutron port dict
        """
        return {"port": self.neutron.create_port(
            network_id=network["network"]["id"], **port_create_args)}

    def _list_ports(self):
        """Return user ports list."""
        return self.neutron.list_ports()

    def _show_port(self, port, **params):
        """Return user port details.

        :param port: dict, neutron port
        :param params: neutron port show options
        :returns: neutron port dict
        """
        return {"port": self.neutron.get_port(port["port"]["id"], **params)}

    def _update_port(self, port, port_update_args):
        """Update the neutron port.

        This atomic function updates port with port_update_args.

        :param port: dict, neutron port
        :param port_update_args: dict, PUT /v2.0/ports update options
        :returns: updated neutron port dict
        """
        port_update_args["name"] = self.generate_random_name()
        return {"port": self.neutron.update_port(port["port"]["id"],
                                                 **port_update_args)}

    def _delete_port(self, port):
        """Delete neutron port.

        :param port: Port object
        """
        self.neutron.delete_port(port["port"]["id"])

    @logging.log_deprecated_args(
        "network_create_args is deprecated; use the network context instead",
        "0.1.0", "network_create_args")
    def _get_or_create_network(self, network_create_args=None):
        """Get a network from context, or create a new one.

        This lets users either create networks with the 'network'
        context, provide existing networks with the 'existing_network'
        context, or let the scenario create a default network for
        them. Running this without one of the network contexts is
        deprecated.

        :param network_create_args: Deprecated way to provide network
                                    creation args; use the network
                                    context instead.
        :returns: Network dict
        """
        if "networks" in self.context["tenant"]:
            return {"network":
                    random.choice(self.context["tenant"]["networks"])}
        else:
            LOG.warning("Running this scenario without either the 'network' "
                        "or 'existing_network' context is deprecated")
            return self._create_network(network_create_args or {})

    def _create_subnets(self, network,
                        subnet_create_args=None,
                        subnet_cidr_start=None,
                        subnets_per_network=1):
        """Create <count> new subnets in the given network.

        :param network: network to create subnets in
        :param subnet_create_args: dict, POST /v2.0/subnets request options
        :param subnet_cidr_start: str, start value for subnets CIDR
        :param subnets_per_network: int, number of subnets for one network
        :returns: List of subnet dicts
        """
        return [self._create_subnet(network, subnet_create_args or {},
                                    subnet_cidr_start)
                for i in range(subnets_per_network)]

    def _create_network_and_subnets(self,
                                    network_create_args=None,
                                    subnet_create_args=None,
                                    subnets_per_network=1,
                                    subnet_cidr_start="1.0.0.0/24"):
        """Create network and subnets.

        :parm network_create_args: dict, POST /v2.0/networks request options
        :parm subnet_create_args: dict, POST /v2.0/subnets request options
        :parm subnets_per_network: int, number of subnets for one network
        :parm subnet_cidr_start: str, start value for subnets CIDR
        :returns: tuple of result network and subnets list
        """
        subnet_create_args = dict(subnet_create_args or {})
        subnet_create_args["start_cidr"] = subnet_cidr_start

        net_topo = self.neutron.create_network_topology(
            network_create_args=(network_create_args or {}),
            subnet_create_args=subnet_create_args,
            subnets_count=subnets_per_network
        )
        subnets = [{"subnet": s} for s in net_topo["subnets"]]
        return {"network": net_topo["network"]}, subnets

    def _create_network_structure(self, network_create_args=None,
                                  subnet_create_args=None,
                                  subnet_cidr_start=None,
                                  subnets_per_network=None,
                                  router_create_args=None):
        """Create a network and a given number of subnets and routers.

        :param network_create_args: dict, POST /v2.0/networks request options
        :param subnet_create_args: dict, POST /v2.0/subnets request options
        :param subnet_cidr_start: str, start value for subnets CIDR
        :param subnets_per_network: int, number of subnets for one network
        :param router_create_args: dict, POST /v2.0/routers request options
        :returns: tuple of (network, subnets, routers)
        """

        subnet_create_args = dict(subnet_create_args or {})
        subnet_create_args["start_cidr"] = subnet_cidr_start

        net_topo = self.neutron.create_network_topology(
            network_create_args=(network_create_args or {}),
            router_create_args=(router_create_args or {}),
            router_per_subnet=True,
            subnet_create_args=subnet_create_args,
            subnets_count=subnets_per_network
        )
        return ({"network": net_topo["network"]},
                [{"subnet": s} for s in net_topo["subnets"]],
                [{"router": r} for r in net_topo["routers"]])

    def _add_interface_router(self, subnet, router):
        """Connect subnet to router.

        :param subnet: dict, neutron subnet
        :param router: dict, neutron router
        """
        self.neutron.add_interface_to_router(router_id=router["id"],
                                             subnet_id=subnet["id"])

    def _remove_interface_router(self, subnet, router):
        """Remove subnet from router

        :param subnet: dict, neutron subnet
        :param router: dict, neutron router
        """
        self.neutron.remove_interface_from_router(
            router_id=router["id"], subnet_id=subnet["id"])

    def _add_gateway_router(self, router, ext_net, enable_snat=None):
        """Set the external network gateway for a router.

        :param router: dict, neutron router
        :param ext_net: external network for the gateway
        :param enable_snat: True if enable snat, None to avoid update
        """
        self.neutron.add_gateway_to_router(
            router_id=router["router"]["id"],
            network_id=ext_net["network"]["id"],
            enable_snat=enable_snat
        )

    def _remove_gateway_router(self, router):
        """Removes an external network gateway from the specified router.

        :param router: dict, neutron router
        """
        self.neutron.remove_gateway_from_router(router["router"]["id"])

    @atomic.action_timer("neutron.create_pool")
    def _create_lb_pool(self, subnet_id, **pool_create_args):
        """Create LB pool(v1)

        :param subnet_id: str, neutron subnet-id
        :param pool_create_args: dict, POST /lb/pools request options
        :returns: dict, neutron lb pool
        """
        args = {"lb_method": self.LB_METHOD,
                "protocol": self.LB_PROTOCOL,
                "name": self.generate_random_name(),
                "subnet_id": subnet_id}
        args.update(pool_create_args)
        return self.clients("neutron").create_pool({"pool": args})

    def _create_v1_pools(self, networks, **pool_create_args):
        """Create LB pools(v1)

        :param networks: list, neutron networks
        :param pool_create_args: dict, POST /lb/pools request options
        :returns: list, neutron lb pools
        """
        subnets = []
        pools = []
        for net in networks:
            subnets.extend(net.get("subnets", []))
        for subnet_id in subnets:
            pools.append(self._create_lb_pool(
                subnet_id, **pool_create_args))
        return pools

    @atomic.action_timer("neutron.list_pools")
    def _list_v1_pools(self, **kwargs):
        """Return user lb pool list(v1)."""
        return self.clients("neutron").list_pools(**kwargs)

    @atomic.action_timer("neutron.delete_pool")
    def _delete_v1_pool(self, pool):
        """Delete neutron pool.

        :param pool: Pool object
        """
        self.clients("neutron").delete_pool(pool["id"])

    @atomic.action_timer("neutron.update_pool")
    def _update_v1_pool(self, pool, **pool_update_args):
        """Update pool.

        This atomic function updates the pool with pool_update_args.

        :param pool: Pool object
        :param pool_update_args: dict, POST /lb/pools update options
        :returns: updated neutron pool dict
        """
        pool_update_args["name"] = self.generate_random_name()
        body = {"pool": pool_update_args}
        return self.clients("neutron").update_pool(pool["pool"]["id"], body)

    def _create_v1_vip(self, pool, **vip_create_args):
        """Create VIP(v1)

        :parm pool: dict, neutron lb-pool
        :parm vip_create_args: dict, POST /lb/vips request options
        :returns: dict, neutron lb vip
        """
        args = {"protocol": self.LB_PROTOCOL,
                "protocol_port": self.LB_PROTOCOL_PORT,
                "name": self.generate_random_name(),
                "pool_id": pool["pool"]["id"],
                "subnet_id": pool["pool"]["subnet_id"]}
        args.update(vip_create_args)
        return self.clients("neutron").create_vip({"vip": args})

    @atomic.action_timer("neutron.list_vips")
    def _list_v1_vips(self, **kwargs):
        """Return user lb vip list(v1)."""
        return self.clients("neutron").list_vips(**kwargs)

    @atomic.action_timer("neutron.delete_vip")
    def _delete_v1_vip(self, vip):
        """Delete neutron vip.

        :param vip: neutron Virtual IP object
        """
        self.clients("neutron").delete_vip(vip["id"])

    @atomic.action_timer("neutron.update_vip")
    def _update_v1_vip(self, vip, **vip_update_args):
        """Updates vip.

        This atomic function updates vip name and admin state

        :param vip: Vip object
        :param vip_update_args: dict, POST /lb/vips update options
        :returns: updated neutron vip dict
        """
        vip_update_args["name"] = self.generate_random_name()
        body = {"vip": vip_update_args}
        return self.clients("neutron").update_vip(vip["vip"]["id"], body)

    def _create_floatingip(self, floating_network, **floating_ip_args):
        """Create floating IP with floating_network.

        :param floating_network: str, external network to create floating IP
        :param floating_ip_args: dict, POST /floatingips create options
        :returns: dict, neutron floating IP
        """

        return {"floatingip": self.neutron.create_floatingip(
            floating_network=floating_network, **floating_ip_args)}

    def _list_floating_ips(self, **kwargs):
        """Return floating IPs list."""
        return {"floatingips": self.neutron.list_floatingips(**kwargs)}

    def _delete_floating_ip(self, floating_ip):
        """Delete floating IP.

        :param dict, floating IP object
        """
        return self.neutron.delete_floatingip(floating_ip["id"])

    def _associate_floating_ip(self, floatingip, port):
        """Associate floating IP with port.

        :param floatingip: floating IP dict
        :param port: port dict
        :returns: updated floating IP dict
        """
        return self.neutron.associate_floatingip(
            port_id=port["id"],
            floatingip_id=floatingip["id"])

    def _dissociate_floating_ip(self, floatingip):
        """Dissociate floating IP from ports.

        :param floatingip: floating IP dict
        :returns: updated floating IP dict
        """
        return self.neutron.dissociate_floatingip(
            floatingip_id=floatingip["id"])

    @atomic.action_timer("neutron.create_healthmonitor")
    def _create_v1_healthmonitor(self, **healthmonitor_create_args):
        """Create LB healthmonitor.

        This atomic function creates healthmonitor with the provided
        healthmonitor_create_args.

        :param healthmonitor_create_args: dict, POST /lb/healthmonitors
        :returns: neutron healthmonitor dict
        """
        args = {"type": self.HM_TYPE,
                "delay": self.HM_DELAY,
                "max_retries": self.HM_MAX_RETRIES,
                "timeout": self.HM_TIMEOUT}
        args.update(healthmonitor_create_args)
        return self.clients("neutron").create_health_monitor(
            {"health_monitor": args})

    @atomic.action_timer("neutron.list_healthmonitors")
    def _list_v1_healthmonitors(self, **kwargs):
        """List LB healthmonitors.

        This atomic function lists all helthmonitors.

        :param kwargs: optional parameters
        :returns: neutron lb healthmonitor list
        """
        return self.clients("neutron").list_health_monitors(**kwargs)

    @atomic.action_timer("neutron.delete_healthmonitor")
    def _delete_v1_healthmonitor(self, healthmonitor):
        """Delete neutron healthmonitor.

        :param healthmonitor: neutron healthmonitor dict
        """
        self.clients("neutron").delete_health_monitor(healthmonitor["id"])

    @atomic.action_timer("neutron.update_healthmonitor")
    def _update_v1_healthmonitor(self, healthmonitor,
                                 **healthmonitor_update_args):
        """Update neutron healthmonitor.

        :param healthmonitor: neutron lb healthmonitor dict
        :param healthmonitor_update_args: POST /lb/healthmonitors
        update options
        :returns: updated neutron lb healthmonitor dict
        """
        body = {"health_monitor": healthmonitor_update_args}
        return self.clients("neutron").update_health_monitor(
            healthmonitor["health_monitor"]["id"], body)

    def _create_security_group(self, **security_group_create_args):
        """Create Neutron security-group.

        :param security_group_create_args: dict, POST /v2.0/security-groups
                                          request options
        :returns: dict, neutron security-group
        """
        security_group_create_args["name"] = self.generate_random_name()
        return {"security_group": self.neutron.create_security_group(
            **security_group_create_args)}

    def _delete_security_group(self, security_group):
        """Delete Neutron security group.

        :param security_group: dict, neutron security_group
        """
        return self.neutron.delete_security_group(
            security_group["security_group"]["id"])

    def _list_security_groups(self, **kwargs):
        """Return list of Neutron security groups."""
        return {"security_groups": self.neutron.list_security_groups(**kwargs)}

    def _show_security_group(self, security_group, **kwargs):
        """Show security group details.

        :param security_group: dict, neutron security_group
        :param kwargs: Optional additional arguments for security_group show
        :returns: security_group details
        """
        return {"security_group": self.neutron.get_security_group(
            security_group["security_group"]["id"], **kwargs)}

    def _update_security_group(self, security_group,
                               **security_group_update_args):
        """Update Neutron security-group.

        :param security_group: dict, neutron security_group
        :param security_group_update_args: dict, POST /v2.0/security-groups
                                           update options
        :returns: dict, updated neutron security-group
        """
        security_group_update_args["name"] = self.generate_random_name()
        return {"security_group": self.neutron.update_security_group(
            security_group["security_group"]["id"],
            **security_group_update_args)}

    def update_loadbalancer_resource(self, lb):
        try:
            new_lb = self.clients("neutron").show_loadbalancer(lb["id"])
        except Exception as e:
            if getattr(e, "status_code", 400) == 404:
                raise exceptions.GetResourceNotFound(resource=lb)
            raise exceptions.GetResourceFailure(resource=lb, err=e)
        return new_lb["loadbalancer"]

    @atomic.action_timer("neutron.create_lbaasv2_loadbalancer")
    def _create_lbaasv2_loadbalancer(self, subnet_id, **lb_create_args):
        """Create LB loadbalancer(v2)

        :param subnet_id: str, neutron subnet-id
        :param lb_create_args: dict, POST /lbaas/loadbalancers request options
        :returns: dict, neutron lb
        """
        args = {"name": self.generate_random_name(),
                "vip_subnet_id": subnet_id}
        args.update(lb_create_args)
        neutronclient = self.clients("neutron")
        lb = neutronclient.create_loadbalancer({"loadbalancer": args})
        lb = lb["loadbalancer"]
        lb = utils.wait_for_status(
            lb,
            ready_statuses=["ACTIVE"],
            status_attr="provisioning_status",
            update_resource=self.update_loadbalancer_resource,
            timeout=CONF.openstack.neutron_create_loadbalancer_timeout,
            check_interval=(
                CONF.openstack.neutron_create_loadbalancer_poll_interval)
        )
        return lb

    @atomic.action_timer("neutron.list_lbaasv2_loadbalancers")
    def _list_lbaasv2_loadbalancers(self, retrieve_all=True, **lb_list_args):
        """List LB loadbalancers(v2)

        :param lb_list_args: dict, POST /lbaas/loadbalancers request options
        :returns: dict, neutron lb loadbalancers(v2)
        """
        return self.clients("neutron").list_loadbalancers(retrieve_all,
                                                          **lb_list_args)

    @atomic.action_timer("neutron.create_bgpvpn")
    def _create_bgpvpn(self, **kwargs):
        """Create Bgpvpn resource (POST /bgpvpn/bgpvpn)

        :param kwargs: optional parameters to create BGP VPN
        :returns dict, bgpvpn resource details
        """
        kwargs["name"] = self.generate_random_name()
        return self.admin_clients("neutron").create_bgpvpn({"bgpvpn": kwargs})

    @atomic.action_timer("neutron.delete_bgpvpn")
    def _delete_bgpvpn(self, bgpvpn):
        """Delete Bgpvpn resource.(DELETE /bgpvpn/bgpvpns/{id})

        :param bgpvpn: dict, bgpvpn
        :return dict, bgpvpn
        """
        return self.admin_clients("neutron").delete_bgpvpn(
            bgpvpn["bgpvpn"]["id"])

    @atomic.action_timer("neutron.list_bgpvpns")
    def _list_bgpvpns(self, **kwargs):
        """Return bgpvpns list.

        :param kwargs: dict, GET /bgpvpn/bgpvpns request options
        :returns: bgpvpns list
        """
        return self.admin_clients("neutron").list_bgpvpns(
            True, **kwargs)["bgpvpns"]

    @atomic.action_timer("neutron.update_bgpvpn")
    def _update_bgpvpn(self, bgpvpn, update_name=False, **kwargs):
        """Update a bgpvpn.

        :param bgpvpn: dict, bgpvpn
        :param update_name: update_name: bool, whether or not to modify
        BGP VPN name
        :param **kwargs: dict, PUT /bgpvpn/bgpvpns update options
        :return dict, updated bgpvpn
        """
        if update_name or "name" in kwargs:
            kwargs["name"] = self.generate_random_name()
        return self.admin_clients("neutron").update_bgpvpn(
            bgpvpn["bgpvpn"]["id"], {"bgpvpn": kwargs})

    @atomic.action_timer("neutron.create_bgpvpn_network_assoc")
    def _create_bgpvpn_network_assoc(self, bgpvpn, network):
        """Creates a new BGP VPN network association.

        :param bgpvpn: dict, bgpvpn
        :param network: dict, network
        :return dict: network_association
        """
        netassoc = {"network_id": network["id"]}
        return self.clients("neutron").create_bgpvpn_network_assoc(
            bgpvpn["bgpvpn"]["id"], {"network_association": netassoc})

    @atomic.action_timer("neutron.delete_bgpvpn_network_assoc")
    def _delete_bgpvpn_network_assoc(self, bgpvpn, net_assoc):
        """Delete the specified BGP VPN network association

        :param bgpvpn: dict, bgpvpn
        :param net_assoc: dict, network
        :return dict: network_association
        """
        return self.clients("neutron").delete_bgpvpn_network_assoc(
            bgpvpn["bgpvpn"]["id"], net_assoc["network_association"]["id"])

    @atomic.action_timer("neutron.create_bgpvpn_router_assoc")
    def _create_bgpvpn_router_assoc(self, bgpvpn, router):
        """Creates a new BGP VPN router association.

        :param bgpvpn: dict, bgpvpn
        :param router: dict, router
        :return dict: network_association
        """
        router_assoc = {"router_id": router["id"]}
        return self.clients("neutron").create_bgpvpn_router_assoc(
            bgpvpn["bgpvpn"]["id"], {"router_association": router_assoc})

    @atomic.action_timer("neutron.delete_bgpvpn_router_assoc")
    def _delete_bgpvpn_router_assoc(self, bgpvpn, router_assoc):
        """Delete the specified BGP VPN router association

        :param bgpvpn: dict, bgpvpn
        :param router_assoc: dict, router
        :return dict: router_association
        """
        return self.clients("neutron").delete_bgpvpn_router_assoc(
            bgpvpn["bgpvpn"]["id"], router_assoc["router_association"]["id"])

    @atomic.action_timer("neutron.list_bgpvpn_network_assocs")
    def _list_bgpvpn_network_assocs(self, bgpvpn, **kwargs):
        """List network association of bgpvpn

        :param bgpvpn: dict, bgpvpn
        :param **kwargs: dict, optional parameters
        :return dict: network_association
        """
        return self.clients("neutron").list_bgpvpn_network_assocs(
            bgpvpn["bgpvpn"]["id"], **kwargs)

    @atomic.action_timer("neutron.list_bgpvpn_router_assocs")
    def _list_bgpvpn_router_assocs(self, bgpvpn, **kwargs):
        """List router association of bgpvpn

        :param bgpvpn: dict, bgpvpn
        :param **kwargs: dict, optional parameters
        :return dict: router_association
        """
        return self.clients("neutron").list_bgpvpn_router_assocs(
            bgpvpn["bgpvpn"]["id"], **kwargs)

    def _create_security_group_rule(self, security_group_id,
                                    **security_group_rule_args):
        """Create Neutron security-group-rule.

        :param security_group_id: id of neutron security_group
        :param security_group_rule_args: dict, POST
              /v2.0/security-group-rules request options
        :returns: dict, neutron security-group-rule
        """
        return {"security_group_rule": self.neutron.create_security_group_rule(
            security_group_id, **security_group_rule_args
        )}

    def _list_security_group_rules(self, **kwargs):
        """List all security group rules.

        :param kwargs: Optional additional arguments for roles list
        :return: list of security group rules
        """
        result = self.neutron.list_security_group_rules(**kwargs)
        return {"security_group_rules": result}

    def _show_security_group_rule(self, security_group_rule, **kwargs):
        """Show information of a given security group rule.

        :param security_group_rule: id of security group rule
        :param kwargs: Optional additional arguments for roles list
        :return: details of security group rule
        """
        return {"security_group_rule": self.neutron.get_security_group_rule(
            security_group_rule, **kwargs)}

    def _delete_security_group_rule(self, security_group_rule):
        """Delete a given security group rule.

        :param security_group_rule: id of security group rule
        """
        self.neutron.delete_security_group_rule(security_group_rule)

    @atomic.action_timer("neutron.delete_trunk")
    def _delete_trunk(self, trunk_port):
        self.clients("neutron").delete_trunk(trunk_port["port_id"])

    @atomic.action_timer("neutron.create_trunk")
    def _create_trunk(self, trunk_payload):
        trunk_payload["name"] = self.generate_random_name()
        return self.clients("neutron").create_trunk({"trunk": trunk_payload})

    @atomic.action_timer("neutron.list_trunks")
    def _list_trunks(self, **kwargs):
        return self.clients("neutron").list_trunks(**kwargs)["trunks"]

    @atomic.action_timer("neutron.list_subports_by_trunk")
    def _list_subports_by_trunk(self, trunk_id):
        return self.clients("neutron").trunk_get_subports(trunk_id)

    @atomic.action_timer("neutron._add_subports_to_trunk")
    def _add_subports_to_trunk(self, trunk_id, subports):
        return self.clients("neutron").trunk_add_subports(
            trunk_id, {"sub_ports": subports})

    def _list_ports_by_device_id(self, device_id):
        return self.neutron.list_ports(device_id=device_id)
