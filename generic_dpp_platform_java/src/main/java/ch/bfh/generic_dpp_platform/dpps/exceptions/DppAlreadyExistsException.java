package ch.bfh.generic_dpp_platform.dpps.exceptions;

public class DppAlreadyExistsException extends RuntimeException {
    public DppAlreadyExistsException(String message) {
        super(message);
    }
}
