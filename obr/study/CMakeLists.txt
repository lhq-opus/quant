cmake_minimum_required(VERSION 3.20)

project(obr_cpp_study LANGUAGES CXX)

option(OBR_STUDY_ENABLE_SANITIZERS
       "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

# 每个教学文件都有自己的 main，所以每个 target 都可以单独运行。
function(add_study_program target_name)
    add_executable(${target_name} ${ARGN})

    set_target_properties(${target_name} PROPERTIES
        CXX_EXTENSIONS OFF
        CXX_STANDARD 11
        CXX_STANDARD_REQUIRED ON
    )

    if(CMAKE_CXX_COMPILER_ID MATCHES "AppleClang|Clang|GNU")
        target_compile_options(${target_name}
            PRIVATE
                -Wall
                -Wextra
                -Wconversion
                -Werror
                -Wpedantic
                -Wshadow
        )
    endif()

    if(OBR_STUDY_ENABLE_SANITIZERS)
        if(CMAKE_CXX_COMPILER_ID MATCHES "AppleClang|Clang|GNU")
            target_compile_options(${target_name}
                PRIVATE
                    -fsanitize=address,undefined
                    -fno-omit-frame-pointer
            )
            target_link_options(${target_name}
                PRIVATE
                    -fsanitize=address,undefined
                    -fno-omit-frame-pointer
            )
        else()
            message(FATAL_ERROR
                    "OBR_STUDY_ENABLE_SANITIZERS is unsupported by this compiler")
        endif()
    endif()
endfunction()

add_study_program(obr_study_01_values
    01_values_references_const.cpp
)

add_study_program(obr_study_02_types
    02_structs_enums_operators.cpp
)

add_study_program(obr_study_03_containers
    03_containers_iterators.cpp
)

add_study_program(obr_study_04_class
    04_class_result_atomicity.cpp
)

add_study_program(obr_study_05_price_time
    05_price_time_queue.cpp
)

# 最后一节不是复制核心：它直接编译正式实现并调用公开接口。
add_study_program(obr_study_06_real_core
    06_use_real_order_book.cpp
    ../src/order_book.cpp
)

target_include_directories(obr_study_06_real_core
    PRIVATE
        ../include
)
