package com.bingo.rng;

import org.apache.commons.rng.core.source64.XoRoShiRo128PlusPlus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.concurrent.ThreadLocalRandom;

@RestController
public class RngController {

    @GetMapping("/random")
    public int generateRandomNumber(
            @RequestParam(defaultValue = "1") int x,
            @RequestParam(defaultValue = "90") int y) {

        if (x <= 0 || y <= 0) {
            throw new IllegalArgumentException("Both x and y must be positive numbers.");
        }

        if (x > y) {
            throw new IllegalArgumentException("Invalid range: x must be less than or equal to y.");
        }

        // Instantiate the generator
        XoRoShiRo128PlusPlus rng = new XoRoShiRo128PlusPlus(new long[]{ThreadLocalRandom.current().nextLong(), ThreadLocalRandom.current().nextLong()});

        // Generate a random integer between x and y
        return (int) (Math.abs(rng.nextLong()) % (y - x + 1)) + x;
    }
}