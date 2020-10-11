"""Diff and DiffElement classes for DSync.

(c) 2020 Network To Code

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

from functools import total_ordering
from typing import Iterator, Iterable, Optional

from .exceptions import ObjectAlreadyExists
from .utils import intersection, OrderedDefaultDict


class Diff:
    """Diff Object, designed to store multiple DiffElement object and organize them in a group."""

    def __init__(self):
        """Initialize a new, empty Diff object."""
        self.children = OrderedDefaultDict(dict)
        """DefaultDict for storing DiffElement objects.

        `self.children[group][unique_id] == DiffElement(...)`
        """

    def complete(self):
        """Method to call when this Diff has been fully populated with data and is "complete".

        The default implementation does nothing, but a subclass could use this, for example, to save
        the completed Diff to a file or database record.
        """

    def add(self, element: "DiffElement"):
        """Add a new DiffElement to the changeset of this Diff.

        Raises:
            ObjectAlreadyExists: if an element of the same type and same name is already stored.
        """
        # Note that element.name is usually a DSyncModel.shortname() -- i.e., NOT guaranteed globally unique!!
        if element.name in self.children[element.type]:
            raise ObjectAlreadyExists(f"Already storing a {element.type} named {element.name}")

        self.children[element.type][element.name] = element

    def groups(self):
        """Get the list of all group keys in self.children."""
        return self.children.keys()

    def has_diffs(self) -> bool:
        """Indicate if at least one of the child elements contains some diff.

        Returns:
            bool: True if at least one child element contains some diff
        """
        for group in self.groups():
            for child in self.children[group].values():
                if child.has_diffs():
                    return True

        return False

    def get_children(self) -> Iterator["DiffElement"]:
        """Iterate over all child elements in all groups in self.children.

        For each group of children, check if an order method is defined,
        Otherwise use the default method.
        """
        order_default = "order_children_default"

        for group in self.groups():
            order_method_name = f"order_children_{group}"
            if hasattr(self, order_method_name):
                order_method = getattr(self, order_method_name)
            else:
                order_method = getattr(self, order_default)

            yield from order_method(self.children[group])

    @classmethod
    def order_children_default(cls, children: dict) -> Iterator["DiffElement"]:
        """Default method to an Iterator for children.

        Since children is already an OrderedDefaultDict, this method is not doing anything special.
        """
        for child in children.values():
            yield child

    def print_detailed(self, indent: int = 0):
        """Print all diffs to screen for all child elements.

        Args:
            indent (int, optional): Indentation to use when printing to screen. Defaults to 0.
        """
        margin = " " * indent
        for group in self.groups():
            print(f"{margin}{group}")
            for child in self.children[group].values():
                if child.has_diffs():
                    child.print_detailed(indent + 2)


@total_ordering
class DiffElement:
    """DiffElement object, designed to represent a single item/object that may or may not have any diffs."""

    def __init__(self, obj_type: str, name: str, keys: dict):
        """Instantiate a DiffElement.

        Args:
            obj_type (str): Name of the object type being described, as in DSyncModel.get_type().
            name (str): Human-readable name of the object being described, as in DSyncModel.get_shortname().
                This name must be unique within the context of the Diff that is the direct parent of this DiffElement.
            keys (dict): Primary keys and values uniquely describing this object, as in DSyncModel.get_identifiers().
        """
        if not isinstance(obj_type, str):
            raise ValueError(f"obj_type must be a string (not {type(obj_type)})")

        if not isinstance(name, str):
            raise ValueError(f"name must be a string (not {type(name)})")

        self.type = obj_type
        self.name = name
        self.keys = keys
        # Note: *_attrs == None if no target object exists; it'll be an empty dict if it exists but has no _attributes
        self.source_attrs: Optional[dict] = None
        self.dest_attrs: Optional[dict] = None
        self.child_diff = Diff()

    def __lt__(self, other):
        """Logical ordering of DiffElements.

        Other comparison methods (__gt__, __le__, __ge__, etc.) are created by our use of the @total_ordering decorator.
        """
        return (self.type, self.name) < (other.type, other.name)

    def __eq__(self, other):
        """Logical equality of DiffElements.

        Other comparison methods (__gt__, __le__, __ge__, etc.) are created by our use of the @total_ordering decorator.
        """
        if not isinstance(other, DiffElement):
            return NotImplemented
        return (
            self.type == other.type
            and self.name == other.name
            and self.keys == other.keys
            and self.source_attrs == other.source_attrs
            and self.dest_attrs == other.dest_attrs
            # TODO also check that self.child_diff == other.child_diff, needs Diff to implement __eq__().
        )

    def __str__(self):
        """Basic string representation of a DiffElement."""
        return f"{self.type} : {self.name} : {self.keys} : {self.source_attrs} : {self.dest_attrs}"

    @property
    def action(self) -> Optional[str]:
        """Action, if any, that should be taken to remediate the diffs described by this element.

        Returns:
            str: "create", "update", "delete", or None
        """
        if self.source_attrs is not None and self.dest_attrs is None:
            return "create"
        if self.source_attrs is None and self.dest_attrs is not None:
            return "delete"
        if (
            self.source_attrs is not None
            and self.dest_attrs is not None
            and any(self.source_attrs[attr_key] != self.dest_attrs[attr_key] for attr_key in self.get_attrs_keys())
        ):
            return "update"

        return None

    # TODO: separate into set_source_attrs() and set_dest_attrs() methods, or just use direct property access instead?
    def add_attrs(self, source: Optional[dict] = None, dest: Optional[dict] = None):
        """Set additional attributes of a source and/or destination item that may result in diffs."""
        # TODO: should source_attrs and dest_attrs be "write-once" properties, or is it OK to overwrite them once set?
        if source is not None:
            self.source_attrs = source

        if dest is not None:
            self.dest_attrs = dest

    def get_attrs_keys(self) -> Iterable[str]:
        """Get the list of shared attrs between source and dest, or the attrs of source or dest if only one is present.

        - If source_attrs is not set, return the keys of dest_attrs
        - If dest_attrs is not set, return the keys of source_attrs
        - If both are defined, return the intersection of both keys
        """
        if self.source_attrs is not None and self.dest_attrs is not None:
            return intersection(self.dest_attrs.keys(), self.source_attrs.keys())
        if self.source_attrs is None and self.dest_attrs is not None:
            return self.dest_attrs.keys()
        if self.source_attrs is not None and self.dest_attrs is None:
            return self.source_attrs.keys()
        return []

    def add_child(self, element: "DiffElement"):
        """Attach a child object of type DiffElement.

        Childs are saved in a Diff object and are organized by type and name.

        Args:
          element: DiffElement
        """
        self.child_diff.add(element)

    def get_children(self) -> Iterator["DiffElement"]:
        """Iterate over all child DiffElements of this one."""
        yield from self.child_diff.get_children()

    def has_diffs(self, include_children: bool = True) -> bool:
        """Check whether this element (or optionally any of its children) has some diffs.

        Args:
          include_children: If True, recursively check children for diffs as well.
        """
        if (self.source_attrs is not None and self.dest_attrs is None) or (
            self.source_attrs is None and self.dest_attrs is not None
        ):
            return True
        if self.source_attrs is not None and self.dest_attrs is not None:
            for attr_key in self.get_attrs_keys():
                if self.source_attrs.get(attr_key) != self.dest_attrs.get(attr_key):
                    return True

        if include_children:
            if self.child_diff.has_diffs():
                return True

        return False

    def print_detailed(self, indent: int = 0):
        """Print status on screen for current object and all children.

        Args:
          indent: Default value = 0
        """
        margin = " " * indent

        if self.source_attrs is None:
            print(f"{margin}{self.type}: {self.name} MISSING in SOURCE")
        elif self.dest_attrs is None:
            print(f"{margin}{self.type}: {self.name} MISSING in DEST")
        else:
            print(f"{margin}{self.type}: {self.name}")
            # Only print attrs that have meaning in both source and dest
            for attr in self.get_attrs_keys():
                if self.source_attrs[attr] != self.dest_attrs[attr]:
                    print(f"{margin}  {attr}   S({self.source_attrs[attr]})   D({self.dest_attrs[attr]})")

        self.child_diff.print_detailed(indent + 2)
