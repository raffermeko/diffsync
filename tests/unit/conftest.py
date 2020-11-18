"""Used to setup fixtures to be used through tests.

Copyright (c) 2020 Network To Code, LLC <info@networktocode.com>

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from typing import ClassVar, List, Mapping, Optional, Tuple

import pytest

from diffsync import DiffSync, DiffSyncModel
from diffsync.diff import Diff, DiffElement
from diffsync.exceptions import ObjectNotCreated, ObjectNotUpdated, ObjectNotDeleted


@pytest.fixture
def generic_diffsync_model():
    """Provide a generic DiffSyncModel instance."""
    return DiffSyncModel()


class ErrorProneModel(DiffSyncModel):
    """Test class that sometimes throws exceptions when creating/updating/deleting instances."""

    _counter: ClassVar[int] = 0

    @classmethod
    def create(cls, diffsync: DiffSync, ids: Mapping, attrs: Mapping):
        """As DiffSyncModel.create(), but periodically throw exceptions."""
        cls._counter += 1
        if not cls._counter % 3:
            raise ObjectNotCreated("Random creation error!")
        return super().create(diffsync, ids, attrs)

    def update(self, attrs: Mapping):
        """As DiffSyncModel.update(), but periodically throw exceptions."""
        # pylint: disable=protected-access
        self.__class__._counter += 1
        if not self.__class__._counter % 3:
            raise ObjectNotUpdated("Random update error!")
        return super().update(attrs)

    def delete(self):
        """As DiffSyncModel.delete(), but periodically throw exceptions."""
        # pylint: disable=protected-access
        self.__class__._counter += 1
        if not self.__class__._counter % 3:
            raise ObjectNotDeleted("Random deletion error!")
        return super().delete()


class Site(DiffSyncModel):
    """Concrete DiffSyncModel subclass representing a site or location that contains devices."""

    _modelname = "site"
    _identifiers = ("name",)
    _children = {"device": "devices"}

    name: str
    devices: List = list()


@pytest.fixture
def make_site():
    """Factory for Site instances."""

    def site(name="site1", devices=None, **kwargs):
        """Provide an instance of a Site model."""
        if not devices:
            devices = []
        return Site(name=name, devices=devices, **kwargs)

    return site


class Device(DiffSyncModel):
    """Concrete DiffSyncModel subclass representing a device."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes: ClassVar[Tuple[str, ...]] = ("role",)
    _children = {"interface": "interfaces"}

    name: str
    site_name: Optional[str]  # note this is not included in _attributes
    role: str
    interfaces: List = list()


@pytest.fixture
def make_device():
    """Factory for Device instances."""

    def device(name="device1", site_name="site1", role="default", **kwargs):
        """Provide an instance of a Device model."""
        return Device(name=name, site_name=site_name, role=role, **kwargs)

    return device


class Interface(DiffSyncModel):
    """Concrete DiffSyncModel subclass representing an interface."""

    _modelname = "interface"
    _identifiers = ("device_name", "name")
    _shortname = ("name",)
    _attributes = ("interface_type", "description")

    device_name: str
    name: str

    interface_type: str = "ethernet"
    description: Optional[str]


@pytest.fixture
def make_interface():
    """Factory for Interface instances."""

    def interface(device_name="device1", name="eth0", **kwargs):
        """Provide an instance of an Interface model."""
        return Interface(device_name=device_name, name=name, **kwargs)

    return interface


@pytest.fixture
def generic_diffsync():
    """Provide a generic DiffSync instance."""
    return DiffSync()


class GenericBackend(DiffSync):
    """An example semi-abstract subclass of DiffSync."""

    site = Site  # to be overridden by subclasses
    device = Device
    interface = Interface

    top_level = ["site"]

    DATA: dict = {}

    def load(self):
        """Initialize the Backend object by loading some site, device and interfaces from DATA."""
        for site_name, site_data in self.DATA.items():
            site = self.site(name=site_name)
            self.add(site)

            for device_name, device_data in site_data.items():
                device = self.device(name=device_name, role=device_data["role"], site_name=site_name)
                self.add(device)
                site.add_child(device)

                for intf_name, desc in device_data["interfaces"].items():
                    intf = self.interface(name=intf_name, device_name=device_name, description=desc)
                    self.add(intf)
                    device.add_child(intf)


class SiteA(Site):
    """Extend Site with a `people` list."""

    _children = {"device": "devices", "person": "people"}

    people: List = list()


class DeviceA(Device):
    """Extend Device with additional data fields."""

    _attributes = ("role", "tag")

    tag: str = ""


class PersonA(DiffSyncModel):
    """Concrete DiffSyncModel subclass representing a person; only used by BackendA."""

    _modelname = "person"
    _identifiers = ("name",)

    name: str


class BackendA(GenericBackend):
    """An example concrete subclass of DiffSync."""

    site = SiteA
    device = DeviceA
    person = PersonA

    DATA = {
        "nyc": {
            "nyc-spine1": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
            "nyc-spine2": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
        },
        "sfo": {
            "sfo-spine1": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
            "sfo-spine2": {"role": "spine", "interfaces": {"eth0": "TBD", "eth1": "ddd", "eth2": "Interface 2"}},
        },
        "rdu": {
            "rdu-spine1": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
            "rdu-spine2": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
        },
    }

    def load(self):
        """Extend the base load() implementation with subclass-specific logic."""
        super().load()
        person = self.person(name="Glenn Matthews")
        self.add(person)
        self.get("site", "rdu").add_child(person)


@pytest.fixture
def backend_a():
    """Provide an instance of BackendA subclass of DiffSync."""
    diffsync = BackendA()
    diffsync.load()
    return diffsync


@pytest.fixture
def backend_a_with_extra_models():
    """Provide an instance of BackendA subclass of DiffSync with some extra sites and devices."""
    extra_models = BackendA()
    extra_models.load()
    extra_site = extra_models.site(name="lax")
    extra_models.add(extra_site)
    extra_device = extra_models.device(name="nyc-spine3", site_name="nyc", role="spine")
    extra_models.get(extra_models.site, "nyc").add_child(extra_device)
    extra_models.add(extra_device)
    return extra_models


@pytest.fixture
def backend_a_minus_some_models():
    """Provide an instance of BackendA subclass of DiffSync with fewer models than the default."""
    missing_models = BackendA()
    missing_models.load()
    missing_models.remove(missing_models.get(missing_models.site, "rdu"))
    missing_device = missing_models.get(missing_models.device, "sfo-spine2")
    missing_models.get(missing_models.site, "sfo").remove_child(missing_device)
    missing_models.remove(missing_device)
    return missing_models


class ErrorProneSiteA(ErrorProneModel, SiteA):
    """A Site that sometimes throws exceptions."""


class ErrorProneDeviceA(ErrorProneModel, DeviceA):
    """A Device that sometimes throws exceptions."""


class ErrorProneInterface(ErrorProneModel, Interface):
    """An Interface that sometimes throws exceptions."""


class ErrorProneBackendA(BackendA):
    """A variant of BackendA that sometimes fails to create/update/delete objects."""

    site = ErrorProneSiteA
    device = ErrorProneDeviceA
    interface = ErrorProneInterface


@pytest.fixture
def error_prone_backend_a():
    """Provide an instance of ErrorProneBackendA subclass of DiffSync."""
    diffsync = ErrorProneBackendA()
    diffsync.load()
    return diffsync


class SiteB(Site):
    """Extend Site with a `places` list."""

    _children = {"device": "devices", "place": "places"}

    places: List = list()


class DeviceB(Device):
    """Extend Device with a `vlans` list."""

    _attributes = ("role", "vlans")

    vlans: List = list()


class PlaceB(DiffSyncModel):
    """Concrete DiffSyncModel subclass representing a place; only used by BackendB."""

    _modelname = "place"
    _identifiers = ("name",)

    name: str


class BackendB(GenericBackend):
    """Another DiffSync concrete subclass with different data from BackendA."""

    site = SiteB
    device = DeviceB
    place = PlaceB

    type = "Backend_B"

    DATA = {
        "nyc": {
            "nyc-spine1": {"role": "spine", "interfaces": {"eth0": "Interface 0/0", "eth1": "Interface 1"}},
            "nyc-spine2": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
        },
        "sfo": {
            "sfo-spine1": {"role": "leaf", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
            "sfo-spine2": {"role": "spine", "interfaces": {"eth0": "TBD", "eth1": "ddd", "eth3": "Interface 3"}},
        },
        "atl": {
            "atl-spine1": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
            "atl-spine2": {"role": "spine", "interfaces": {"eth0": "Interface 0", "eth1": "Interface 1"}},
        },
    }

    def load(self):
        """Extend the base load() implementation with subclass-specific logic."""
        super().load()
        place = self.place(name="Statue of Liberty")
        self.add(place)
        self.get("site", "nyc").add_child(place)


@pytest.fixture
def backend_b():
    """Provide an instance of BackendB subclass of DiffSync."""
    diffsync = BackendB(name="backend-b")
    diffsync.load()
    return diffsync


class TrackedDiff(Diff):
    """Subclass of Diff that knows when it's completed."""

    is_complete: bool = False

    def complete(self):
        """Function called when the Diff has been fully constructed and populated with data."""
        self.is_complete = True


@pytest.fixture
def diff_with_children():
    """Provide a Diff which has multiple children, some of which have children of their own."""
    diff = Diff()

    # person_element_1 only exists in the source
    person_element_1 = DiffElement("person", "Jimbo", {"name": "Jimbo"})
    person_element_1.add_attrs(source={})
    diff.add(person_element_1)

    # person_element_2 only exists in the dest
    person_element_2 = DiffElement("person", "Sully", {"name": "Sully"})
    person_element_2.add_attrs(dest={})
    diff.add(person_element_2)

    # device_element has no diffs of its own, but has a child intf_element
    device_element = DiffElement("device", "device1", {"name": "device1"})
    diff.add(device_element)

    # intf_element exists in both source and dest as a child of device_element, and has differing attrs
    intf_element = DiffElement("interface", "eth0", {"device_name": "device1", "name": "eth0"})
    source_attrs = {"interface_type": "ethernet", "description": "my interface"}
    dest_attrs = {"description": "your interface"}
    intf_element.add_attrs(source=source_attrs, dest=dest_attrs)
    device_element.add_child(intf_element)

    # address_element exists in both source and dest but has no diffs
    address_element = DiffElement("address", "RTP", {"name": "RTP"})
    address_element.add_attrs(source={"state": "NC"}, dest={"state": "NC"})
    diff.add(address_element)

    return diff
