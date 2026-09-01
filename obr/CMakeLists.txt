cmake_minimum_required(VERSION 3.20)

project(obr LANGUAGES CXX)

option(OBR_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

add_library(obr_reconstruction_core
    src/order_book.cpp
)

target_include_directories(obr_reconstruction_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

set_target_properties(obr_reconstruction_core PROPERTIES
    CXX_EXTENSIONS OFF
    CXX_STANDARD 11
    CXX_STANDARD_REQUIRED ON
)

if(CMAKE_CXX_COMPILER_ID MATCHES "AppleClang|Clang|GNU")
    target_compile_options(obr_reconstruction_core
        PRIVATE
            -Wall
            -Wextra
            -Wconversion
            -Werror
            -Wpedantic
            -Wshadow
    )
endif()

if(OBR_ENABLE_SANITIZERS)
    if(CMAKE_CXX_COMPILER_ID MATCHES "AppleClang|Clang|GNU")
        target_compile_options(obr_reconstruction_core
            PUBLIC
                -fsanitize=address,undefined
                -fno-omit-frame-pointer
        )
        target_link_options(obr_reconstruction_core
            PUBLIC
                -fsanitize=address,undefined
                -fno-omit-frame-pointer
        )
    else()
        message(FATAL_ERROR "OBR_ENABLE_SANITIZERS is unsupported by this compiler")
    endif()
endif()

add_executable(obr_validate_reconstruction_core
    validation/reconstruction_core_validation.cpp
)

target_link_libraries(obr_validate_reconstruction_core
    PRIVATE
        obr_reconstruction_core
)

set_target_properties(obr_validate_reconstruction_core PROPERTIES
    CXX_EXTENSIONS OFF
    CXX_STANDARD 11
    CXX_STANDARD_REQUIRED ON
)

if(CMAKE_CXX_COMPILER_ID MATCHES "AppleClang|Clang|GNU")
    target_compile_options(obr_validate_reconstruction_core
        PRIVATE
            -Wall
            -Wextra
            -Wconversion
            -Werror
            -Wpedantic
            -Wshadow
    )
endif()
