# Python basics

## Lists and tuples
A list is mutable: its contents can be changed after creation. A tuple is
immutable: its elements cannot be reassigned. Use a list for a collection you
intend to modify. A tuple can represent a fixed collection. An immutable tuple
can still contain a mutable object, such as a list; that inner list can change.

## Dictionaries
A dictionary maps unique, hashable keys to values. Square-bracket lookup,
such as user["name"], raises KeyError when the key is absent. The get method
returns None for a missing key unless you supply another default, for example
user.get("name", "Guest"). A normal list is unhashable and cannot be a dictionary
key. A tuple is hashable only if all its elements are hashable.

## Loops
A for loop iterates over an iterable. range(3) produces 0, 1, and 2: the stop
value is excluded. The break statement exits the innermost loop. The continue
statement skips the remainder of the current iteration and proceeds with the
next iteration. For example, looping over range(4) and skipping the value 1
visits the remaining values 0, 2, and 3.

## Functions
The return statement sends a value back to the caller and exits the function.
The print function displays output; it does not replace returning a result.
A function that reaches its end without return returns None. Default argument
values are evaluated once when the function is defined. A mutable default list
can therefore be shared across calls. Use None as the default and create a new
list inside the function when you need a fresh list for each call.

## Exceptions
Use try and except to handle exceptions. ValueError commonly means that an
argument has an appropriate type but an inappropriate value, such as int("cat").
Catch the specific exception you expect so that unrelated errors remain visible.
The finally block runs when control leaves the try statement during normal
execution or exception handling, including when a return statement is executed.
