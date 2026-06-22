<?php
function demo_greet(string $name): string {
    return "Hello, $name!";
}

echo demo_greet("world");
